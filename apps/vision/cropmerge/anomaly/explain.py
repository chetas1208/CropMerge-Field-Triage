from __future__ import annotations

from cropmerge.anomaly.grid import GridCell

# Same blend as review_priority — surfaced in copy so farmers see the math.
REVIEW_SCORE_ANOMALY_WEIGHT = 0.65
REVIEW_SCORE_PERSISTENCE_WEIGHT = 0.35


def combined_review_score(anomaly: float, persistence: float) -> float:
    return REVIEW_SCORE_ANOMALY_WEIGHT * anomaly + REVIEW_SCORE_PERSISTENCE_WEIGHT * persistence


def _pct_delta(value: float) -> str:
    sign = "+" if value > 0 else "−" if value < 0 else ""
    return f"{sign}{abs(value):.0%}"


def _pct_share(value: float) -> str:
    return f"{max(0.0, min(1.0, value)):.0%}"


def _loc_label(location: str | None) -> str:
    if not location:
        return "this patch"
    return location.replace("_", " ").replace("-", " ").lower()


def explain_cell(cell: GridCell, cfg: dict, persistence: float | None = None) -> list[str]:
    """Human-readable, number-backed reasons — pilot briefing tone, not agronomy claims."""
    min_c = float(cfg.get("anomaly", {}).get("reason_contribution_min", 0.08))
    reasons: list[str] = []
    feats = cell.features
    contrib = cell.contributions

    if contrib.get("coverage", 0) >= min_c:
        delta = float(feats.get("coverage_delta", 0.0))
        crop = float(feats.get("crop_coverage", 0.0))
        bare = float(feats.get("bare_soil", 0.0))
        if delta < -0.05:
            reasons.append(
                f"Canopy looks thinner than the field norm ({_pct_delta(delta)} vs baseline; "
                f"{_pct_share(crop)} crop cover here, {_pct_share(bare)} bare soil visible)"
            )
        elif delta > 0.05:
            reasons.append(
                f"Greener / denser strip than the surrounding rows ({_pct_delta(delta)} vs baseline; "
                f"{_pct_share(crop)} crop cover in this cell)"
            )
        else:
            reasons.append(
                f"Crop cover sits off the field median ({_pct_share(crop)} here vs typical patch mix)"
            )

    if contrib.get("color", 0) >= min_c:
        lab = float(feats.get("color_difference", 0.0))
        reasons.append(
            f"RGB color profile diverges from the field median (Lab distance {lab:.2f} — "
            "think lighter/darker or shifted hue, not a diagnosis)"
        )

    if contrib.get("vegetation", 0) >= min_c:
        exg = float(feats.get("exg_difference", feats.get("vegetation_difference", 0.0)))
        reasons.append(
            f"Greenness proxy (ExG) is off the field baseline by {exg:.2f} — "
            "visible vegetation signal only, not NDVI"
        )

    if contrib.get("texture", 0) >= min_c:
        tex = float(feats.get("texture_difference", 0.0))
        reasons.append(
            f"Surface texture / edge pattern differs from neighboring crop ({tex:.2f} texture delta — "
            "could be row spacing, residue, or trampling)"
        )

    if contrib.get("dino", 0) >= min_c:
        emb = float(feats.get("embedding_difference", 0.0))
        reasons.append(
            f"Patch looks visually unlike the dominant field texture (embedding distance {emb:.2f})"
        )

    if contrib.get("isolation", 0) >= min_c:
        reasons.append(
            "Multivariate fingerprint is an outlier — several cues stack up in the same grid cell"
        )

    if persistence is not None and persistence >= 0.5:
        reasons.append(
            f"Not a one-frame glitch — pattern held for ~{persistence:.0%} of sampled timestamps "
            "as the drone moved"
        )

    return reasons


def review_priority(score: float, persistence: float, cfg: dict) -> str:
    hi = float(cfg.get("anomaly", {}).get("high_threshold", 0.65))
    mid = float(cfg.get("anomaly", {}).get("medium_threshold", 0.40))
    combined = combined_review_score(score, persistence)
    if combined >= hi:
        return "high"
    if combined >= mid:
        return "medium"
    return "low"


def recommendation(
    priority: str,
    *,
    location: str | None = None,
    anomaly_score: float = 0.0,
    persistence: float = 0.0,
    frames_seen: int = 0,
) -> str:
    loc = _loc_label(location)
    review = combined_review_score(anomaly_score, persistence)
    frame_note = f" flagged in {frames_seen} frames" if frames_seen else ""

    if priority == "high":
        return (
            f"Fly the {loc} sector on your next pass — review score {review:.0%} "
            f"({REVIEW_SCORE_ANOMALY_WEIGHT:.0%} visual oddity + "
            f"{REVIEW_SCORE_PERSISTENCE_WEIGHT:.0%} stickiness{frame_note}). "
            "Drop to tree-top height or walk the rows before you blame crop stress."
        )
    if priority == "medium":
        return (
            f"Bookmark the {loc} area for the next flight (review score {review:.0%}). "
            "If it still pops on a repeat pass, worth boots-on-the-ground photos — "
            "could be drainage, compaction, or just a hybrid line."
        )
    return (
        f"Low-key variation in the {loc} — review score {review:.0%}. "
        "Optional drive-by; skip unless you're already scouting nearby."
    )
