from __future__ import annotations

from cropmerge.anomaly.grid import GridCell


def explain_cell(cell: GridCell, cfg: dict, persistence: float | None = None) -> list[str]:
    """Human-readable reasons only for meaningful contributors."""
    min_c = float(cfg.get("anomaly", {}).get("reason_contribution_min", 0.08))
    reasons: list[str] = []
    feats = cell.features
    contrib = cell.contributions

    if contrib.get("coverage", 0) >= min_c:
        delta = feats.get("coverage_delta", 0.0)
        if delta < -0.05:
            reasons.append(
                f"Lower visible crop coverage than the field baseline ({delta:.0%} coverage delta)"
            )
        elif delta > 0.05:
            reasons.append(
                f"Higher visible crop coverage than the field baseline (+{delta:.0%} coverage delta)"
            )
        else:
            reasons.append("Crop coverage differs from the field baseline")

    if contrib.get("color", 0) >= min_c:
        reasons.append("Color distribution (Lab) differs from surrounding crop appearance")

    if contrib.get("vegetation", 0) >= min_c:
        reasons.append("RGB vegetation proxy (ExG) differs from field median — not NDVI")

    if contrib.get("texture", 0) >= min_c:
        reasons.append("Local texture/edge structure differs from field baseline")

    if contrib.get("dino", 0) >= min_c:
        reasons.append("Visual embedding differs from dominant field appearance")

    if contrib.get("isolation", 0) >= min_c:
        reasons.append("Multivariate pattern is unusual versus other field cells")

    if persistence is not None and persistence >= 0.5:
        reasons.append("Visual difference persists across multiple analyzed frames")

    return reasons


def review_priority(score: float, persistence: float, cfg: dict) -> str:
    hi = float(cfg.get("anomaly", {}).get("high_threshold", 0.65))
    mid = float(cfg.get("anomaly", {}).get("medium_threshold", 0.40))
    combined = 0.65 * score + 0.35 * persistence
    if combined >= hi:
        return "high"
    if combined >= mid:
        return "medium"
    return "low"


def recommendation(priority: str) -> str:
    if priority == "high":
        return (
            "Inspect this area at closer range. "
            "Use higher-resolution or multispectral imagery before drawing crop-health conclusions."
        )
    if priority == "medium":
        return "Review this zone on the next field pass; confirm whether variation is persistent on the ground."
    return "Low priority visual variation — optional ground check if nearby."
