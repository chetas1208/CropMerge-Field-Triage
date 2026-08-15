from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from cropmerge.anomaly.explain import explain_cell, recommendation, review_priority
from cropmerge.anomaly.grid import GridCell
from cropmerge.pipeline.schemas import (
    InspectionZone,
    RelativeLocation,
    ReviewPriority,
    ZoneEvidence,
)


def relative_location(cx: float, cy: float) -> RelativeLocation:
    """cx, cy in [0,1] image-normalized."""
    col = 0 if cx < 1 / 3 else (2 if cx > 2 / 3 else 1)
    row = 0 if cy < 1 / 3 else (2 if cy > 2 / 3 else 1)
    grid = [
        [RelativeLocation.NW, RelativeLocation.N, RelativeLocation.NE],
        [RelativeLocation.W, RelativeLocation.C, RelativeLocation.E],
        [RelativeLocation.SW, RelativeLocation.S, RelativeLocation.SE],
    ]
    return grid[row][col]


@dataclass
class _Track:
    id: str
    centroids: list[tuple[float, float]] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)
    cells: list[GridCell] = field(default_factory=list)
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)


def _centroid_norm(cell: GridCell, h: int, w: int) -> tuple[float, float]:
    cx = ((cell.x0 + cell.x1) / 2) / max(w, 1)
    cy = ((cell.y0 + cell.y1) / 2) / max(h, 1)
    return cx, cy


def _bbox_norm(cell: GridCell, h: int, w: int) -> tuple[float, float, float, float]:
    return cell.x0 / w, cell.y0 / h, (cell.x1 - cell.x0) / w, (cell.y1 - cell.y0) / h


def aggregate_zones(
    frame_cells: list[list[GridCell]],
    timestamps: list[float],
    quality_weights: list[float],
    frame_shape: tuple[int, int],
    cfg: dict,
) -> list[InspectionZone]:
    """Link high-scoring cells across time → persistent inspection zones."""
    tcfg = cfg.get("temporal", {})
    acfg = cfg.get("anomaly", {})
    min_frames = int(tcfg.get("min_persistent_frames", 3))
    link_dist = float(tcfg.get("centroid_link_distance", 0.12))
    score_gate = float(acfg.get("medium_threshold", 0.40)) * 0.85
    mid_thr = float(acfg.get("medium_threshold", 0.40))
    h, w = frame_shape

    tracks: list[_Track] = []
    next_id = 1

    for cells, ts, qw in zip(frame_cells, timestamps, quality_weights):
        # Keep only local peaks per frame (top-k) to avoid grid spam
        ranked = sorted(
            [c for c in cells if c.valid and c.anomaly_score >= score_gate],
            key=lambda c: c.anomaly_score,
            reverse=True,
        )
        candidates = ranked[:6]
        used_tracks: set[int] = set()
        for cell in sorted(candidates, key=lambda c: c.anomaly_score, reverse=True):
            cx, cy = _centroid_norm(cell, h, w)
            best_i, best_d = -1, 1e9
            for i, tr in enumerate(tracks):
                if i in used_tracks or not tr.centroids:
                    continue
                px, py = tr.centroids[-1]
                d = float(np.hypot(cx - px, cy - py))
                if d < best_d:
                    best_d, best_i = d, i
            weighted_score = cell.anomaly_score * float(qw)
            if best_i >= 0 and best_d <= link_dist:
                tr = tracks[best_i]
                tr.centroids.append((cx, cy))
                tr.scores.append(weighted_score)
                tr.weights.append(float(qw))
                tr.timestamps.append(ts)
                tr.cells.append(cell)
                tr.bboxes.append(_bbox_norm(cell, h, w))
                used_tracks.add(best_i)
            else:
                tid = f"ZONE_{next_id:03d}"
                next_id += 1
                tracks.append(
                    _Track(
                        id=tid,
                        centroids=[(cx, cy)],
                        scores=[weighted_score],
                        weights=[float(qw)],
                        timestamps=[ts],
                        cells=[cell],
                        bboxes=[_bbox_norm(cell, h, w)],
                    )
                )

    zones: list[InspectionZone] = []
    for tr in tracks:
        if len(tr.timestamps) < min_frames:
            continue
        mean_score = float(np.average(tr.scores, weights=np.maximum(tr.weights, 1e-3)))
        if mean_score < mid_thr * 0.9:
            continue
        span = max(tr.timestamps) - min(tr.timestamps)
        persistence = float(
            np.clip(len(tr.timestamps) / max(len(timestamps), 1), 0.0, 1.0)
        )
        if span > 0 and len(timestamps) > 1:
            persistence = float(
                np.clip(
                    0.5 * persistence
                    + 0.5 * (span / max(timestamps[-1] - timestamps[0], 1e-3)),
                    0,
                    1,
                )
            )
        cx = float(np.mean([c[0] for c in tr.centroids]))
        cy = float(np.mean([c[1] for c in tr.centroids]))
        rep = tr.cells[int(np.argmax(tr.scores))]
        reasons = explain_cell(rep, cfg, persistence=persistence)
        if not reasons:
            continue
        pri = review_priority(mean_score, persistence, cfg)
        bb = tr.bboxes[int(np.argmax(tr.scores))]
        cov_deltas = [c.features.get("coverage_delta", 0.0) for c in tr.cells]
        zones.append(
            InspectionZone(
                id=tr.id,
                review_priority=ReviewPriority(pri),
                anomaly_score=round(float(np.clip(mean_score, 0, 1)), 4),
                persistence_score=round(persistence, 4),
                first_seen_ms=round(min(tr.timestamps) * 1000, 1),
                last_seen_ms=round(max(tr.timestamps) * 1000, 1),
                first_seen_sec=round(min(tr.timestamps), 3),
                last_seen_sec=round(max(tr.timestamps), 3),
                frames_seen=len(tr.timestamps),
                relative_location=relative_location(cx, cy),
                centroid_norm={"x": round(cx, 4), "y": round(cy, 4)},
                bbox_norm={
                    "x": round(bb[0], 4),
                    "y": round(bb[1], 4),
                    "w": round(bb[2], 4),
                    "h": round(bb[3], 4),
                },
                evidence=ZoneEvidence(
                    crop_coverage_delta=round(float(np.mean(cov_deltas)), 4),
                    color_difference=round(float(rep.features.get("color_difference", 0)), 4),
                    vegetation_difference=round(
                        float(rep.features.get("vegetation_difference", 0)), 4
                    ),
                    texture_difference=round(float(rep.features.get("texture_difference", 0)), 4),
                    embedding_difference=round(
                        float(rep.features.get("embedding_difference", 0)), 4
                    ),
                    persistence=round(persistence, 4),
                ),
                reasons=reasons,
                recommendation=recommendation(pri),
            )
        )

    # Prefer high priority, then score; cap for product UI
    zones.sort(
        key=lambda z: (
            {"high": 2, "medium": 1, "low": 0}[z.review_priority.value],
            z.anomaly_score,
            z.persistence_score,
        ),
        reverse=True,
    )
    return zones[:12]
