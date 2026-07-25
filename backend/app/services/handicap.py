from __future__ import annotations

import math


HANDICAP_CLASSES = (
    "modern_topless",
    "high_performance_kingpost",
    "intermediate_kingpost",
    "single_surface",
)
DEFAULT_PILOT_CLASS = HANDICAP_CLASSES[0]
DEFAULT_HANDICAP_MULTIPLIERS = {pilot_class: 1.0 for pilot_class in HANDICAP_CLASSES}


def handicap_config(penalties_json: object) -> tuple[bool, dict[str, float]]:
    handicap = penalties_json.get("handicap") if isinstance(penalties_json, dict) else None
    enabled = handicap.get("enabled") is True if isinstance(handicap, dict) else False
    configured = handicap.get("multipliers") if isinstance(handicap, dict) else None
    multipliers = dict(DEFAULT_HANDICAP_MULTIPLIERS)
    if isinstance(configured, dict):
        for pilot_class in HANDICAP_CLASSES:
            value = configured.get(pilot_class)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
                multipliers[pilot_class] = float(value)
    return enabled, multipliers


def validate_handicap_config(penalties_json: dict) -> dict:
    if "handicap" not in penalties_json:
        return penalties_json
    handicap = penalties_json["handicap"]
    if not isinstance(handicap, dict) or not isinstance(handicap.get("enabled"), bool):
        raise ValueError("handicap.enabled must be true or false")
    multipliers = handicap.get("multipliers")
    if not isinstance(multipliers, dict):
        raise ValueError("handicap.multipliers must contain all four pilot classes")
    for pilot_class in HANDICAP_CLASSES:
        value = multipliers.get(pilot_class)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"handicap multiplier for {pilot_class} must be a positive number")
    return penalties_json
