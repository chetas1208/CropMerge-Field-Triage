from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from cropmerge import DEFAULT_LIMITATIONS, DISCLAIMER
from cropmerge.anomaly.spatial import score_frame
from cropmerge.anomaly.temporal import aggregate_zones
from cropmerge.config import load_config
from cropmerge.features.dinov3 import create_embedder
from cropmerge.pipeline.schemas import (
    AnalysisSummary,
    ArtifactPaths,
    FieldSummary,
    FieldTriageReport,
    VideoSourceMeta,
)
from cropmerge.segmentation import create_segmenter
from cropmerge.segmentation.postprocess import class_fractions
from cropmerge.video.decoder import sample_frames
from cropmerge.video.quality import analyze_sequence
from cropmerge.video.registration import estimate_homography
from cropmerge.visualization.heatmap import accumulate_heatmaps, render_heatmap
from cropmerge.visualization.overlay import annotate_frame
from cropmerge.visualization.video_writer import write_image, write_video

log = logging.getLogger("cropmerge.pipeline")


def _device_str() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class FieldTriageProcessor:
    """End-to-end RGB drone video → inspection zones + artifacts."""

    def __init__(self, config: dict | None = None, config_path: str | Path | None = None):
        self.cfg = config or load_config(config_path)

    def process(
        self,
        input_path: str | Path,
        output_dir: str | Path,
        *,
        sample_fps: float | None = None,
        max_frames: int | None = None,
        skip_dino: bool | None = None,
        segmentation_backend: str | None = None,
        dino_backend: str | None = None,
        run_id: str | None = None,
    ) -> FieldTriageReport:
        t0 = time.perf_counter()
        latency: dict[str, float] = {}
        input_path = Path(input_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        run_id = run_id or uuid.uuid4().hex[:12]
        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = run_dir / "frames"
        overlays_dir = run_dir / "overlays"
        frames_dir.mkdir(exist_ok=True)
        overlays_dir.mkdir(exist_ok=True)

        vcfg = self.cfg.setdefault("video", {})
        sample_fps = float(sample_fps if sample_fps is not None else vcfg.get("sample_fps", 2.0))
        max_frames = max_frames if max_frames is not None else vcfg.get("max_frames", 120)
        import os

        seg_backend = (
            segmentation_backend
            or os.environ.get("CROP_MERGE_SEGMENTATION_BACKEND")
            or self.cfg.get("segmentation", {}).get("backend")
            or "field_cv"
        )
        dino_be = (
            dino_backend
            or os.environ.get("CROP_MERGE_DINO_BACKEND")
            or self.cfg.get("features", {}).get("dino_backend")
            or "auto"
        )
        if skip_dino is None:
            skip_dino = bool(self.cfg.get("features", {}).get("skip_dino", False))

        # --- decode ---
        t = time.perf_counter()
        frames, meta = sample_frames(input_path, sample_fps=sample_fps, max_frames=max_frames)
        assert isinstance(meta, VideoSourceMeta)
        latency["video_decode"] = time.perf_counter() - t
        log.info("Decoded %d frames from %s", len(frames), input_path.name)

        # --- quality ---
        t = time.perf_counter()
        qualities = analyze_sequence(frames, self.cfg)
        latency["quality_analysis"] = time.perf_counter() - t
        usable_n = sum(1 for q in qualities if q.usable)

        # --- segmentation (field_cv / sam2 / heuristic) ---
        t = time.perf_counter()
        segmenter = create_segmenter(seg_backend, self.cfg, allow_fallback=True)
        segmenter.start_video([f.bgr for f in frames])
        segs = segmenter.track_video([(f.index, f.timestamp_sec) for f in frames])
        segmenter.close()
        latency["segmentation"] = time.perf_counter() - t
        used_fallback = any(s.is_fallback for s in segs) or seg_backend in {"heuristic", "mock"}
        log.info(
            "Segmentation backend=%s fallback=%s",
            segs[0].backend if segs else seg_backend,
            used_fallback,
        )

        # --- registration between consecutive frames ---
        t = time.perf_counter()
        reg_confs: list[float] = []
        regs = []
        for i in range(1, len(frames)):
            reg = estimate_homography(frames[i - 1].bgr, frames[i].bgr, self.cfg)
            reg_confs.append(reg.confidence if reg.success else 0.0)
            regs.append(reg)
        latency["registration"] = time.perf_counter() - t

        # --- embeddings + spatial anomaly ---
        t = time.perf_counter()
        rows = int(self.cfg.get("grid", {}).get("rows", 8))
        cols = int(self.cfg.get("grid", {}).get("cols", 8))
        emb_name = "heuristic" if skip_dino else dino_be
        embedder = create_embedder(emb_name, allow_fallback=True)
        actual_dino = "skipped" if skip_dino else embedder.name
        log.info("Embedding backend=%s", actual_dino)

        frame_cells = []
        heats = []
        qweights = []
        for fr, seg, q in zip(frames, segs, qualities):
            field = (
                seg.field_mask
                if seg.field_mask is not None
                else np.zeros(fr.bgr.shape[:2], dtype=bool)
            )
            label = (
                seg.label_map
                if seg.label_map is not None
                else np.full(fr.bgr.shape[:2], "UNKNOWN", dtype=object)
            )
            emb = embedder.embed_tiles(fr.bgr, field, rows, cols)
            cells, heat = score_frame(fr.bgr, field, label, emb, self.cfg)
            # Quality weighting (blur/exposure reduce temporal influence)
            qw = float(q.quality_weight)
            if qw < 1.0:
                heat = heat * qw
                for c in cells:
                    c.anomaly_score *= qw
            frame_cells.append(cells)
            heats.append(heat)
            qweights.append(qw)
        latency["feature_anomaly"] = time.perf_counter() - t

        # --- temporal consensus → inspection zones ---
        t = time.perf_counter()
        h, w = frames[0].bgr.shape[:2]
        zones = aggregate_zones(
            frame_cells,
            [f.timestamp_sec for f in frames],
            qweights,
            (h, w),
            self.cfg,
        )
        # Quality- and registration-weighted mean heatmap for export
        fused_heat = None
        if heats:
            acc = np.zeros_like(heats[0], dtype=np.float64)
            wsum = 0.0
            for i, ht in enumerate(heats):
                conf = reg_confs[i - 1] if i > 0 and i - 1 < len(reg_confs) else 1.0
                ww = float(qweights[i]) * (0.5 + 0.5 * conf)
                acc += ht.astype(np.float64) * ww
                wsum += ww
            if wsum > 0:
                fused_heat = (acc / wsum).astype(np.float32)
        latency["temporal_consensus"] = time.perf_counter() - t
        log.info("Inspection zones: %d", len(zones))

        # --- field summary ---
        crop_covs, bare_covs, field_fracs = [], [], []
        road = tree = water = infra = False
        class_acc: dict[str, list[float]] = {}
        for seg in segs:
            if seg.label_map is None:
                continue
            fracs = class_fractions(seg.label_map)
            for k, v in fracs.items():
                if k.startswith("_"):
                    continue
                class_acc.setdefault(k, []).append(v)
            if seg.field_mask is not None:
                field_fracs.append(float(np.mean(seg.field_mask)))
            crop_covs.append(fracs.get("CROP", 0.0))
            bare_covs.append(fracs.get("BARE_SOIL", 0.0))
            road = road or fracs.get("ROAD_PATH", 0) > 0.01
            tree = tree or fracs.get("TREE_VEGETATION", 0) > 0.01
            water = water or fracs.get("WATER", 0) > 0.005
            infra = infra or fracs.get("INFRASTRUCTURE", 0) > 0.005

        mean_field = float(np.mean(field_fracs)) if field_fracs else 0.0
        field_detected = mean_field >= 0.08 and (float(np.mean(crop_covs)) if crop_covs else 0) + (
            float(np.mean(bare_covs)) if bare_covs else 0
        ) >= 0.05

        if not field_detected:
            zones = []
            log.warning("No field detected — suppressing inspection zones")

        field_summary = FieldSummary(
            detected=field_detected,
            mean_crop_coverage=round(float(np.mean(crop_covs)) if crop_covs else 0.0, 4),
            mean_bare_soil=round(float(np.mean(bare_covs)) if bare_covs else 0.0, 4),
            road_path_detected=road,
            tree_vegetation_detected=tree,
            water_detected=water,
            infrastructure_detected=infra,
            mean_field_fraction=round(mean_field, 4),
        )
        class_coverage = {k: round(float(np.mean(v)), 4) for k, v in class_acc.items()}

        # --- render ---
        t = time.perf_counter()
        annotated = []
        for fr, seg in zip(frames, segs):
            ann = annotate_frame(
                fr.bgr,
                seg.label_map,
                seg.field_mask,
                zones if field_detected else [],
                fr.timestamp_sec,
                self.cfg,
            )
            annotated.append(ann)
            if self.cfg.get("output", {}).get("write_frames", True):
                write_image(frames_dir / f"frame_{fr.index:04d}.jpg", fr.bgr)
                write_image(overlays_dir / f"overlay_{fr.index:04d}.jpg", ann)

        ann_path = None
        if self.cfg.get("output", {}).get("write_annotated_video", True):
            ann_path = str(run_dir / "annotated_video.mp4")
            write_video(annotated, ann_path, fps=sample_fps)

        heat_path = None
        acc_heat = fused_heat if fused_heat is not None else accumulate_heatmaps(heats, qweights)
        heat_img = render_heatmap(acc_heat, frames[len(frames) // 2].bgr)
        if self.cfg.get("output", {}).get("write_heatmap", True):
            heat_path = str(run_dir / "heatmap.png")
            write_image(heat_path, heat_img)

        # montage: first / mid / last overlay
        if len(annotated) >= 1:
            picks = [0, len(annotated) // 2, len(annotated) - 1]
            mont = np.hstack([cv2.resize(annotated[i], (320, 240)) for i in picks])
            write_image(run_dir / "segmentation_montage.jpg", mont)

        latency["rendering"] = time.perf_counter() - t
        total = time.perf_counter() - t0
        latency["total_runtime"] = total

        limitations = list(DEFAULT_LIMITATIONS)
        if used_fallback:
            limitations.append(
                f"Segmentation backend '{seg_backend}' used fallback/heuristic path — not claimed as SAM 3.1 output"
            )
        if skip_dino or actual_dino == "heuristic":
            limitations.append(
                "Dense embeddings used heuristic descriptors — not claimed as DINOv3 unless backend bound"
            )
        if not field_detected:
            limitations.append("No field detected in sampled frames")
        if reg_confs and float(np.mean(reg_confs)) < 0.3:
            limitations.append("Low average registration confidence between frames")

        results_path = str(run_dir / "results.json")
        metrics_path = str(run_dir / "metrics.json")
        artifacts = ArtifactPaths(
            results_json=results_path,
            annotated_video=ann_path,
            heatmap_png=heat_path,
            metrics_json=metrics_path,
            frames_dir=str(frames_dir),
            overlays_dir=str(overlays_dir),
        )

        report = FieldTriageReport(
            schema_version="1.0",
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            disclaimer=DISCLAIMER,
            source=meta,
            analysis=AnalysisSummary(
                frames_sampled=len(frames),
                frames_usable=usable_n,
                sample_fps=sample_fps,
                segmentation_backend=segs[0].backend if segs else seg_backend,
                dino_backend=actual_dino,
                used_fallback=used_fallback,
                device=_device_str(),
                stage_latency_sec={k: round(v, 4) for k, v in latency.items()},
                total_runtime_sec=round(total, 4),
            ),
            field=field_summary,
            inspection_zones=zones,
            frame_quality=qualities,
            class_coverage=class_coverage,
            limitations=limitations,
            artifacts=artifacts,
            georeferenced=False,
            map_label="Annotated fly-through — boxes mark zones that stuck around frame-to-frame",
        )

        camel = report.to_camel_dict()
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(camel, f, indent=2)
        if self.cfg.get("output", {}).get("write_metrics", True):
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "run_id": run_id,
                        "stage_latency_sec": latency,
                        "frames_sampled": len(frames),
                        "frames_usable": usable_n,
                        "zones": len(zones),
                        "registration_mean_confidence": round(float(np.mean(reg_confs)) if reg_confs else 0.0, 4),
                        "used_fallback": used_fallback,
                    },
                    f,
                    indent=2,
                )
        log.info("Done run_id=%s total=%.2fs zones=%d", run_id, total, len(zones))
        try:
            from cropmerge.db import record_run

            record_run(report, status="completed")
        except Exception as e:
            log.warning("DB write skipped: %s", e)
        return report
