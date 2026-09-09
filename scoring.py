"""
scoring.py
----------
Implements the decision logic we finalized:

  - Tier 3 (reverse geocoding) FAIL  -> automatic FLAG, severity "high"
  - Weather MAJOR mismatch alone      -> automatic FLAG, severity "high"
  - Both together                     -> FLAG, severity "critical"
  - Everything else (Tier 4, minor weather mismatch, OCR/vision
    disagreement, missing EXIF, etc.) contributes to a soft confidence
    score but does NOT trigger an automatic flag on its own.
"""


def determine_flag(tier3_result, weather_mismatch_level):
    """
    tier3_result: "PASS" or "FAIL"
    weather_mismatch_level: "MATCH" / "MINOR_MISMATCH" / "MAJOR_MISMATCH" / "N/A"

    Returns (flagged: bool, severity: str, flag_reason: str)
    """
    tier3_failed = (tier3_result == "FAIL")
    weather_major = (weather_mismatch_level == "MAJOR_MISMATCH")

    if tier3_failed and weather_major:
        return True, "critical", "Tier 3 FAIL + Major weather mismatch (two independent hard signals)"

    if tier3_failed:
        return True, "high", "Tier 3 FAIL: claimed coordinates failed reverse geocoding plausibility check"

    if weather_major:
        return True, "high", "Major weather mismatch between claimed record and photo"

    return False, "none", ""


def soft_confidence_score(checks):
    """
    Combines the non-auto-flagging signals into a 0-1 confidence score.
    'checks' is a dict of individual results already computed elsewhere,
    e.g.:
      {
        "tier1_agreement": "AGREE" | "DISAGREE" | "PARTIAL" | "N/A",
        "tier4_result": "MATCH" | "MISMATCH" | "N/A",
        "weather_mismatch_level": "MATCH" | "MINOR_MISMATCH" | "N/A" | "MAJOR_MISMATCH",
        "exif_gps_present": bool,
        "exif_gps_distance_m": float or None,
        "lighting_check_result": "PASS" | "FAIL" | "N/A",
      }

    Only signals that actually returned a result are counted (weights
    are re-normalised over whatever is available) - so a claim isn't
    penalised just because, say, Street View coverage doesn't exist
    for that address.
    """
    # (signal_name, weight, pass_condition)
    weight_table = [
        ("tier1_agreement", 0.25, lambda v: v == "AGREE"),
        ("tier4_result", 0.15, lambda v: v == "MATCH"),
        ("weather_mismatch_level", 0.20, lambda v: v == "MATCH"),
        ("exif_match", 0.25, lambda v: v is True),
        ("lighting_check_result", 0.15, lambda v: v == "PASS"),
    ]

    # Derive a simple exif_match bool from the raw distance, if EXIF exists
    exif_match = None
    if checks.get("exif_gps_present"):
        dist = checks.get("exif_gps_distance_m")
        exif_match = (dist is not None and dist <= 300)  # matches config.EXIF_GPS_DISTANCE_THRESHOLD_M
    checks = dict(checks)
    checks["exif_match"] = exif_match

    total_weight = 0.0
    earned_weight = 0.0
    signals_used = 0

    for key, weight, passes in weight_table:
        value = checks.get(key)
        if value in (None, "N/A", "N-A"):
            continue  # signal unavailable - skip it, don't penalise
        total_weight += weight
        signals_used += 1
        if passes(value):
            earned_weight += weight

    if total_weight == 0:
        return 0.0, "no_signals_available"

    score = round(earned_weight / total_weight, 2)
    evidence_level = (
        "full evidence" if signals_used >= 4 else
        "partial evidence" if signals_used >= 2 else
        "baseline evidence only"
    )
    return score, evidence_level
