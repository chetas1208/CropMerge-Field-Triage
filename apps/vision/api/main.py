from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from cropmerge import __version__
from cropmerge.config import load_config
from cropmerge.db import list_runs
from cropmerge.features.dinov3 import dinov3_available
from cropmerge.logging_utils import setup_logging
from cropmerge.pipeline.processor import FieldTriageProcessor
from cropmerge.segmentation.sam3 import sam3_available

try:
    from cropmerge.features.dinov2 import dinov2_available
except Exception:  # pragma: no cover
    def dinov2_available() -> bool:  # type: ignore
        return False

try:
    from cropmerge.segmentation.sam2 import sam2_available
except Exception:  # pragma: no cover
    def sam2_available() -> bool:  # type: ignore
        return False

setup_logging(os.environ.get("CROP_MERGE_LOG_LEVEL", "INFO"))

app = FastAPI(
    title="CropMerge Vision Engine",
    version=__version__,
    description="Internal CV inference service. Product API lives in Nuxt.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_ROOT = Path(os.environ.get("CROP_MERGE_OUTPUTS", Path(__file__).resolve().parents[3] / "outputs")).resolve()
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def _torch_ok() -> bool:
    try:
        import torch  # noqa: F401

        return True
    except ImportError:
        return False


def _ffmpeg_ok() -> bool:
    return shutil.which("ffmpeg") is not None or shutil.which("ffprobe") is not None


def _opencv_ok() -> bool:
    try:
        import cv2  # noqa: F401

        return True
    except ImportError:
        return False


def _device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


class AnalyzeOptions(BaseModel):
    sample_fps: float = 2.0
    max_frames: int | None = 120
    skip_dino: bool = False
    segmentation_backend: str = Field(default_factory=lambda: os.environ.get("CROP_MERGE_SEGMENTATION_BACKEND", "heuristic"))
    dino_backend: str = Field(default_factory=lambda: os.environ.get("CROP_MERGE_DINO_BACKEND", "heuristic"))
    debug: bool = False


@app.get("/vision/health")
def health():
    seg = os.environ.get("CROP_MERGE_SEGMENTATION_BACKEND", "heuristic")
    dino = os.environ.get("CROP_MERGE_DINO_BACKEND", "heuristic")
    ok_core = _opencv_ok()
    db_path = os.environ.get("VISION_DATABASE_URL") or str(
        Path(os.environ.get("DATABASE_DIR", Path(__file__).resolve().parents[3] / "data" / "db"))
        / "vision.sqlite"
    )
    return {
        "status": "ok" if ok_core else "degraded",
        "version": __version__,
        "device": _device(),
        "segmentationBackend": seg,
        "dinoBackend": dino,
        "samAvailable": sam3_available(),
        "sam2Available": sam2_available(),
        "dinoAvailable": dinov3_available(),
        "dinov2Available": dinov2_available(),
        "torchAvailable": _torch_ok(),
        "opencvAvailable": _opencv_ok(),
        "ffmpegAvailable": _ffmpeg_ok(),
        "databaseUrl": db_path,
    }


@app.get("/vision/runs")
def runs(limit: int = 20):
    return {"runs": list_runs(limit=min(max(limit, 1), 100))}


@app.post("/vision/analyze")
async def analyze(
    file: UploadFile = File(...),
    sample_fps: float = Form(2.0),
    max_frames: int = Form(120),
    skip_dino: bool = Form(False),
    segmentation_backend: str = Form("heuristic"),
    dino_backend: str = Form("heuristic"),
):
    suffix = Path(file.filename or "upload.mp4").suffix.lower()
    allowed = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    if suffix not in allowed:
        raise HTTPException(400, f"Unsupported type: {suffix}. Use video (.mp4/.mov/.m4v) or image (.jpg/.png/.webp).")

    run_id = uuid.uuid4().hex[:12]
    tmp = Path(tempfile.mkdtemp(prefix="cropmerge_"))
    try:
        in_path = tmp / f"input{suffix}"
        data = await file.read()
        if not data:
            raise HTTPException(400, "Empty upload")
        in_path.write_bytes(data)

        cfg = load_config()
        proc = FieldTriageProcessor(cfg)
        report = proc.process(
            in_path,
            OUTPUT_ROOT,
            sample_fps=sample_fps,
            max_frames=max_frames if max_frames > 0 else None,
            skip_dino=skip_dino,
            segmentation_backend=segmentation_backend,
            dino_backend=dino_backend,
            run_id=run_id,
        )
        return report.to_camel_dict()
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, f"Vision pipeline failed: {e}") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@app.post("/vision/segment")
async def segment_only(file: UploadFile = File(...)):
    """Lightweight single-image segmentation for debugging."""
    import numpy as np
    import cv2
    from cropmerge.segmentation import create_segmenter
    from cropmerge.config import load_config

    data = await file.read()
    arr = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise HTTPException(400, "Could not decode image")
    cfg = load_config()
    seg = create_segmenter(os.environ.get("CROP_MERGE_SEGMENTATION_BACKEND", "heuristic"), cfg)
    result = seg.segment_image(bgr, 0, 0.0)
    fracs = {}
    if result.label_map is not None:
        from cropmerge.segmentation.postprocess import class_fractions

        fracs = {k: v for k, v in class_fractions(result.label_map).items() if not k.startswith("_")}
    return {
        "backend": result.backend,
        "isFallback": result.is_fallback,
        "fieldDetected": bool(result.field_mask is not None and float(np.mean(result.field_mask)) > 0.05),
        "classCoverage": fracs,
    }


@app.post("/vision/anomaly")
async def anomaly_note():
    return {
        "message": "Use POST /vision/analyze for full spatial+temporal anomaly pipeline",
    }


@app.get("/vision/artifacts/{run_id}/{name}")
def get_artifact(run_id: str, name: str):
    # Prevent path traversal
    if ".." in run_id or ".." in name or "/" in run_id:
        raise HTTPException(400, "Invalid path")
    path = (OUTPUT_ROOT / run_id / name).resolve()
    if not str(path).startswith(str(OUTPUT_ROOT)):
        raise HTTPException(400, "Invalid path")
    if not path.is_file():
        raise HTTPException(404, "Artifact not found")
    return FileResponse(path)
