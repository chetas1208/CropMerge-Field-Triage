#!/usr/bin/env python3
"""Synthetic Midwest-like field flight for offline demo (no copyrighted footage)."""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def make_frame(t: float, w: int = 640, h: int = 360) -> np.ndarray:
    """Procedural field: green crop, soil patch anomaly, dirt road, trees."""
    y, x = np.mgrid[0:h, 0:w]
    # Pan slowly
    shift = int(20 * np.sin(t * 0.7))
    xx = x + shift

    # Base crop green with high-frequency rows (sharper Laplacian)
    row = 25 * (((xx // 4 + y // 3) % 2) * 2 - 1)
    g = 110 + 35 * np.sin((xx + y * 0.2) / 6.0) + 12 * np.sin(y / 15.0) + row * 0.35
    r = 45 + 12 * np.sin(xx / 22.0)
    b = 40 + 10 * np.cos(y / 18.0)
    img = np.stack([b, g, r], axis=-1).astype(np.float32)

    # Bare soil patch (persistent anomaly NE) — strong color break
    cy, cx = int(0.28 * h), int(0.72 * w) + shift // 2
    soil = ((y - cy) ** 2 / (50 ** 2) + (x - cx) ** 2 / (60 ** 2)) < 1.0
    img[soil] = np.array([55, 100, 170], dtype=np.float32)  # BGR brown

    # Secondary weak anomaly (lower crop density SW)
    cy2, cx2 = int(0.72 * h), int(0.25 * w)
    thin = ((y - cy2) ** 2 / (40 ** 2) + (x - cx2) ** 2 / (48 ** 2)) < 1.0
    img[thin] = img[thin] * 0.4 + np.array([45, 65, 120], dtype=np.float32) * 0.6

    # Dirt road horizontal band
    road = (y > h * 0.55) & (y < h * 0.62) & (x > w * 0.05) & (x < w * 0.95)
    img[road] = np.array([75, 90, 105], dtype=np.float32)
    img[road] += (((x[road] // 3) % 2) * 8 - 4)[:, None]

    # Tree line top
    trees = (y < h * 0.12) & (np.sin(x / 10.0) > -0.15)
    img[trees] = np.array([20, 50, 15], dtype=np.float32)

    rng = np.random.default_rng(int(t * 1000) % 10000)
    img += rng.normal(0, 4.0, img.shape).astype(np.float32)
    out = np.clip(img, 0, 255).astype(np.uint8)
    # Rare mild blur only
    if int(t * 10) % 23 == 0:
        out = cv2.GaussianBlur(out, (3, 3), 0)
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--output", default=None)
    p.add_argument("--seconds", type=float, default=6.0)
    p.add_argument("--fps", type=float, default=10.0)
    args = p.parse_args()
    out = Path(args.output or Path(__file__).resolve().parents[1] / "samples" / "synthetic_field.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    w, h = 640, 360
    n = int(args.seconds * args.fps)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out), fourcc, args.fps, (w, h))
    if not writer.isOpened():
        raise SystemExit("VideoWriter failed")
    for i in range(n):
        t = i / args.fps
        writer.write(make_frame(t, w, h))
    writer.release()
    print(f"Wrote {out} ({n} frames @ {args.fps} fps)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
