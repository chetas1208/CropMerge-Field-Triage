from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

import cv2

from cropmerge.pipeline.schemas import VideoSourceMeta

log = logging.getLogger("cropmerge.video.metadata")


def _ffprobe(path: Path) -> dict:
    if not shutil.which("ffprobe"):
        return {}
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
        return json.loads(out)
    except (subprocess.CalledProcessError, json.JSONDecodeError, OSError) as e:
        log.warning("ffprobe failed for %s: %s", path, e)
        return {}


def _opencv_meta(path: Path) -> dict:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {path}")
    meta = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0),
        "fps": float(cap.get(cv2.CAP_PROP_FPS) or 0.0),
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
    }
    cap.release()
    if meta["fps"] <= 1e-3:
        meta["fps"] = 30.0
    if meta["frame_count"] <= 0 and meta["fps"] > 0:
        meta["frame_count"] = 0
    meta["duration_sec"] = (
        meta["frame_count"] / meta["fps"] if meta["fps"] > 0 else 0.0
    )
    return meta


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}


def _image_meta(path: Path) -> dict:
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(f"Cannot open image: {path}")
    h, w = bgr.shape[:2]
    return {
        "width": int(w),
        "height": int(h),
        "fps": 1.0,
        "frame_count": 1,
        "duration_sec": 0.0,
    }


def extract_metadata(path: str | Path) -> VideoSourceMeta:
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    suffix = path.suffix.lower()
    if suffix not in VIDEO_EXTS | IMAGE_EXTS:
        raise ValueError(f"Unsupported media extension: {path.suffix}")

    if suffix in IMAGE_EXTS:
        cv = _image_meta(path)
        return VideoSourceMeta(
            filename=path.name,
            path=str(path),
            duration_sec=float(cv["duration_sec"]),
            width=int(cv["width"]),
            height=int(cv["height"]),
            fps=float(cv["fps"]),
            frame_count=int(cv["frame_count"]),
            codec="image",
            orientation=None,
            created_at=None,
            gps=None,
        )

    cv = _opencv_meta(path)
    probe = _ffprobe(path)
    codec = None
    created = None
    orientation = None
    gps = None

    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            codec = stream.get("codec_name")
            tags = stream.get("tags") or {}
            rot = tags.get("rotate") or stream.get("rotation")
            if rot is not None:
                try:
                    orientation = int(float(rot))
                except (TypeError, ValueError):
                    pass
            break

    fmt = probe.get("format") or {}
    tags = fmt.get("tags") or {}
    created = tags.get("creation_time") or tags.get("com.apple.quicktime.creationdate")
    # GPS hooks for future DJI telemetry — never assumed present
    lat = tags.get("location") or tags.get("com.apple.quicktime.location.ISO6709")
    if isinstance(lat, str) and lat.startswith("+") or (isinstance(lat, str) and lat.startswith("-")):
        gps = {"latitude": None, "longitude": None, "altitude": None}

    width = int(cv["width"] or 0)
    height = int(cv["height"] or 0)
    fps = float(cv["fps"] or 0.0)
    frame_count = int(cv["frame_count"] or 0)
    duration = float(cv["duration_sec"] or 0.0)
    if duration <= 0 and fmt.get("duration"):
        try:
            duration = float(fmt["duration"])
            if frame_count <= 0 and fps > 0:
                frame_count = int(round(duration * fps))
        except (TypeError, ValueError):
            pass

    return VideoSourceMeta(
        filename=path.name,
        path=str(path),
        duration_sec=duration,
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        codec=codec,
        orientation=orientation,
        created_at=created,
        gps=gps,
    )
