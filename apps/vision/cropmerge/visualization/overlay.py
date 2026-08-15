from __future__ import annotations

import cv2
import numpy as np

from cropmerge.pipeline.schemas import InspectionZone, SemanticClass
from cropmerge.segmentation.labels import CLASS_COLORS_BGR


def draw_segmentation(bgr: np.ndarray, label_map: np.ndarray, opacity: float = 0.35) -> np.ndarray:
    out = bgr.copy()
    overlay = bgr.copy()
    for cls, color in CLASS_COLORS_BGR.items():
        if cls == SemanticClass.UNKNOWN:
            continue
        sel = label_map == cls.value
        overlay[sel] = color
    return cv2.addWeighted(overlay, opacity, out, 1.0 - opacity, 0)


def draw_field_boundary(bgr: np.ndarray, field_mask: np.ndarray) -> np.ndarray:
    out = bgr.copy()
    if field_mask is None or not np.any(field_mask):
        return out
    cnts, _ = cv2.findContours(field_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, cnts, -1, (0, 255, 255), 2)
    return out


def draw_zones(bgr: np.ndarray, zones: list[InspectionZone], opacity: float = 0.45) -> np.ndarray:
    out = bgr.copy()
    h, w = out.shape[:2]
    colors = {"high": (0, 0, 255), "medium": (0, 165, 255), "low": (0, 255, 255)}
    for z in zones:
        bb = z.bbox_norm
        x0 = int(bb["x"] * w)
        y0 = int(bb["y"] * h)
        x1 = int((bb["x"] + bb["w"]) * w)
        y1 = int((bb["y"] + bb["h"]) * h)
        color = colors.get(z.review_priority.value, (0, 255, 255))
        overlay = out.copy()
        cv2.rectangle(overlay, (x0, y0), (x1, y1), color, -1)
        out = cv2.addWeighted(overlay, opacity * 0.35, out, 1 - opacity * 0.35, 0)
        cv2.rectangle(out, (x0, y0), (x1, y1), color, 2)
        label = f"{z.id} {z.review_priority.value.upper()}"
        cv2.putText(out, label, (x0 + 4, max(16, y0 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)
    return out


def draw_legend(bgr: np.ndarray) -> np.ndarray:
    out = bgr.copy()
    items = [
        ("CROP", CLASS_COLORS_BGR[SemanticClass.CROP]),
        ("SOIL", CLASS_COLORS_BGR[SemanticClass.BARE_SOIL]),
        ("ROAD", CLASS_COLORS_BGR[SemanticClass.ROAD_PATH]),
        ("TREE", CLASS_COLORS_BGR[SemanticClass.TREE_VEGETATION]),
        ("WATER", CLASS_COLORS_BGR[SemanticClass.WATER]),
    ]
    x, y = 10, 20
    cv2.rectangle(out, (5, 5), (150, 20 + 18 * len(items)), (0, 0, 0), -1)
    for name, color in items:
        cv2.rectangle(out, (x, y - 10), (x + 14, y + 4), color, -1)
        cv2.putText(out, name, (x + 20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        y += 18
    return out


def draw_timestamp(bgr: np.ndarray, t: float) -> np.ndarray:
    out = bgr.copy()
    m = int(t // 60)
    s = t - m * 60
    text = f"{m:02d}:{s:04.1f}"
    cv2.putText(out, text, (out.shape[1] - 100, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return out


def annotate_frame(
    bgr: np.ndarray,
    label_map: np.ndarray | None,
    field_mask: np.ndarray | None,
    zones: list[InspectionZone],
    timestamp_sec: float,
    cfg: dict,
) -> np.ndarray:
    vcfg = cfg.get("visualization", {})
    out = bgr.copy()
    if label_map is not None:
        out = draw_segmentation(out, label_map, float(vcfg.get("mask_opacity", 0.35)))
    if field_mask is not None:
        out = draw_field_boundary(out, field_mask)
    out = draw_zones(out, zones, float(vcfg.get("zone_opacity", 0.45)))
    if vcfg.get("draw_legend", True):
        out = draw_legend(out)
    out = draw_timestamp(out, timestamp_sec)
    # Disclaimer strip
    cv2.putText(
        out,
        "Exploratory RGB visual analysis — not agronomic diagnosis",
        (10, out.shape[0] - 12),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (220, 220, 220),
        1,
        cv2.LINE_AA,
    )
    return out
