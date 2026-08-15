from __future__ import annotations

import cv2
import numpy as np

from cropmerge.pipeline.schemas import SemanticClass
from cropmerge.segmentation.base import FrameSegmentation, SegmentMask
from cropmerge.segmentation.labels import CLASS_PRIORITY


def resolve_overlaps(masks: list[SegmentMask], shape: tuple[int, int]) -> np.ndarray:
    """Build exclusive label map; higher priority classes win."""
    h, w = shape
    label_map = np.full((h, w), SemanticClass.UNKNOWN.value, dtype=object)
    priority = np.zeros((h, w), dtype=np.int16)
    for m in sorted(masks, key=lambda x: CLASS_PRIORITY.get(x.label, 0)):
        if m.mask is None or m.mask.shape[:2] != (h, w):
            continue
        sel = m.mask.astype(bool)
        p = CLASS_PRIORITY.get(m.label, 0)
        win = sel & (p >= priority)
        label_map[win] = m.label.value
        priority[win] = p
    return label_map


def build_field_mask(label_map: np.ndarray, union_classes: list[str] | None = None) -> np.ndarray:
    union = set(union_classes or ["CROP", "BARE_SOIL", "FIELD"])
    field = np.isin(label_map, list(union))
    # Morphological clean
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    field_u8 = field.astype(np.uint8) * 255
    field_u8 = cv2.morphologyEx(field_u8, cv2.MORPH_CLOSE, k, iterations=2)
    field_u8 = cv2.morphologyEx(field_u8, cv2.MORPH_OPEN, k, iterations=1)
    # Largest component preference
    n, labels, stats, _ = cv2.connectedComponentsWithStats((field_u8 > 0).astype(np.uint8), 8)
    if n <= 1:
        return field_u8 > 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    keep = 1 + int(np.argmax(areas))
    # Keep components >= 15% of largest
    thr = 0.15 * areas.max()
    out = np.zeros_like(field_u8, dtype=bool)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= thr:
            out[labels == i] = True
    return out


def finalize_segmentation(seg: FrameSegmentation, cfg: dict) -> FrameSegmentation:
    if not seg.masks:
        h = seg.label_map.shape[0] if seg.label_map is not None else 0
        w = seg.label_map.shape[1] if seg.label_map is not None else 0
        if h == 0:
            return seg
    shape = seg.masks[0].mask.shape[:2] if seg.masks else seg.label_map.shape[:2]
    seg.label_map = resolve_overlaps(seg.masks, shape)
    union = cfg.get("segmentation", {}).get("field_union_classes", ["CROP", "BARE_SOIL", "FIELD"])
    seg.field_mask = build_field_mask(seg.label_map, union)
    seg.crop_mask = seg.label_map == SemanticClass.CROP.value
    return seg


def class_fractions(label_map: np.ndarray) -> dict[str, float]:
    flat = label_map.reshape(-1)
    total = max(flat.size, 1)
    out: dict[str, float] = {}
    for c in SemanticClass:
        out[c.value] = float(np.mean(flat == c.value))
    out["_total_pixels"] = float(total)
    return out
