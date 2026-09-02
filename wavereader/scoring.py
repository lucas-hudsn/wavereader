"""Deterministic surf-quality scoring module.

Provides non-linear, robust surf quality evaluations calibrated by surfer skill level.
Calculates component scores (0.0 to 10.0) using continuous curves and physics-aware decay.
"""

from __future__ import annotations

import math
from typing import TypedDict, Any, Dict, List, Tuple, Optional

# ---- 16-Point Compass Reference ----

_COMPASS_DEG: dict[str, float] = {
    "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
    "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
    "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
    "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
}

_WEIGHTS = {
    "swell_size": 0.30,
    "swell_direction": 0.20,
    "wind": 0.30,
    "period": 0.20,
}

# Skill Profile Thresholds (values in feet, knots, seconds)
_SKILL_PROFILES: dict[str, dict[str, Any]] = {
    "beginner": {
        "comfort_size_min_ft": 1.0,
        "comfort_size_max_ft": 3.5,
        "max_safe_size_ft": 4.5,
        "max_wind_kt": 12.0,
        "ideal_period_max_s": 12.0,
    },
    "intermediate": {
        "comfort_size_min_ft": 2.0,
        "comfort_size_max_ft": 6.5,
        "max_safe_size_ft": 8.5,
        "max_wind_kt": 18.0,
        "ideal_period_max_s": 16.0,
    },
    "advanced": {
        "comfort_size_min_ft": 3.0,
        "comfort_size_max_ft": 12.0,
        "max_safe_size_ft": 18.0,
        "max_wind_kt": 25.0,
        "ideal_period_max_s": 22.0,
    },
    "expert": {
        "comfort_size_min_ft": 4.0,
        "comfort_size_max_ft": 30.0,
        "max_safe_size_ft": 50.0,
        "max_wind_kt": 35.0,
        "ideal_period_max_s": 25.0,
    },
}

SKILL_LEVELS = tuple(_SKILL_PROFILES.keys())
_DEFAULT_SKILL_LEVEL = "intermediate"

# ---- Helpers ----

def _dir_to_deg(direction: str) -> float:
    """Parses cardinal strings, slash-separated, or 'to' directions to degrees."""
    normalized = direction.replace(",", "/").replace(" to ", "/").replace(" ", "").upper()
    parts = normalized.split("/")
    degs = [_COMPASS_DEG[p] for p in parts if p in _COMPASS_DEG]
    if not degs:
        raise ValueError(f"Invalid compass direction input: {direction!r}")
    
    # Cyclic mean for angles
    sin_sum = sum(math.sin(math.radians(d)) for d in degs)
    cos_sum = sum(math.cos(math.radians(d)) for d in degs)
    mean_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
    return round(mean_deg, 1)


def _angular_diff(a: float, b: float) -> float:
    """Calculates shortest arc distance between two bearings in degrees."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _gaussian_decay(value: float, target: float, sigma: float) -> float:
    """Smooth Gaussian decay yielding 1.0 at target and trailing to 0.0."""
    return math.exp(-((value - target) ** 2) / (2 * (sigma ** 2)))


# ---- Core Scoring Components ----

def _score_swell_size(wave_height_m: float, spot: dict, skill_level: str) -> float:
    """Evaluates swell size considering spot ideals and surfer safety constraints."""
    profile = _SKILL_PROFILES[skill_level]
    wave_height_ft = wave_height_m * 3.28084
    
    spot_ideal = spot["ideal_swell"]
    spot_min_ft = float(spot_ideal["size_ft_min"])
    spot_max_ft = float(spot_ideal["size_ft_max"])

    # 1. Spot Suitability (Does the spot work?)
    if spot_min_ft <= wave_height_ft <= spot_max_ft:
        spot_score = 10.0
    elif wave_height_ft < spot_min_ft:
        sigma = max(1.0, spot_min_ft * 0.4)
        spot_score = 10.0 * _gaussian_decay(wave_height_ft, spot_min_ft, sigma)
    else:
        sigma = max(1.5, spot_max_ft * 0.5)
        spot_score = 10.0 * _gaussian_decay(wave_height_ft, spot_max_ft, sigma)

    # 2. Safety & Comfort Filter
    comf_min = profile["comfort_size_min_ft"]
    comf_max = profile["comfort_size_max_ft"]
    max_safe = profile["max_safe_size_ft"]

    if wave_height_ft > max_safe:
        # Zero tolerance for dangerous wave heights relative to skill
        return 0.0
    
    skill_mult = 1.0
    if wave_height_ft < comf_min:
        skill_mult = max(0.2, wave_height_ft / comf_min)
    elif wave_height_ft > comf_max:
        # Smooth penalty down to zero at max_safe_size
        overage = wave_height_ft - comf_max
        allowed_headroom = max_safe - comf_max
        skill_mult = max(0.0, 1.0 - (overage / allowed_headroom) ** 1.5)

    return round(spot_score * skill_mult, 2)


def _score_swell_direction(wave_dir_deg: float, spot: dict) -> float:
    """Calculates directional match relative to optimal spot window."""
    ideal_deg = _dir_to_deg(spot["ideal_swell"]["direction"])
    diff = _angular_diff(wave_dir_deg, ideal_deg)
    
    # Half-width tolerance angle before severe drop-off (e.g., 45 degrees)
    tolerance_deg = 45.0
    score = 10.0 * _gaussian_decay(diff, 0.0, tolerance_deg / 1.5)
    return max(0.0, min(10.0, score))


def _score_wind(
    wind_speed_kt: float,
    wind_dir_deg: float,
    spot: dict,
    skill_level: str = _DEFAULT_SKILL_LEVEL,
) -> float:
    """Scores wind as the mean of a speed score and a direction score.

    Speed: glassy (<= 5 kt) is always perfect; above the tolerable limit
    (the spot's ``strength_kt_max``, capped by the skill profile) it scores 0.
    Direction: cosine falloff from perfect offshore to absolute onshore.
    """
    profile_max = _SKILL_PROFILES[skill_level]["max_wind_kt"]
    spot_max = float(spot["ideal_wind"]["strength_kt_max"])
    limit = min(spot_max, profile_max)

    offshore_dir_deg = _dir_to_deg(spot["ideal_wind"]["direction"])
    diff = _angular_diff(wind_dir_deg, offshore_dir_deg)
    dir_score = 10.0 * max(0.0, math.cos(math.radians(diff / 2.0)))

    if wind_speed_kt <= 5.0:
        speed_score = 10.0  # glassy regardless of direction
    elif wind_speed_kt <= limit:
        speed_score = 10.0
    else:
        speed_score = 0.0

    return round((speed_score + dir_score) / 2.0, 2)


def _score_period(period_s: float) -> float:
    """Evaluates swell period quality: 0 below 4 s, 10 from 14 s up.

    Long groundswell is never penalised — there is no falloff above 14 s.
    """
    if period_s <= 4.0:
        return 0.0
    if period_s >= 14.0:
        return 10.0
    return round(10.0 * (period_s - 4.0) / 10.0, 2)


# ---- Main Interface Functions ----

def score_hour(
    wave_height_m: float,
    wave_period_s: float,
    wind_speed_kt: float,
    wind_direction_deg: float,
    spot: dict,
    wave_direction_deg: Optional[float] = None,
    skill_level: str = _DEFAULT_SKILL_LEVEL,
) -> dict[str, Any]:
    """Computes composite surf score (0-10) for a given hour and skill tier."""
    if skill_level not in _SKILL_PROFILES:
        raise ValueError(f"Invalid skill_level {skill_level!r}. Expected one of {SKILL_LEVELS}")

    c_size = _score_swell_size(wave_height_m, spot, skill_level)
    c_dir = (
        _score_swell_direction(wave_direction_deg, spot)
        if wave_direction_deg is not None
        else None
    )
    c_wind = _score_wind(wind_speed_kt, wind_direction_deg, spot, skill_level)
    c_period = _score_period(wave_period_s)

    components: dict[str, Optional[float]] = {
        "swell_size": round(c_size, 2),
        "swell_direction": round(c_dir, 2) if c_dir is not None else None,
        "wind": round(c_wind, 2),
        "period": round(c_period, 2),
    }

    # Weight redistribution when optional components are missing
    active_weights = {k: v for k, v in _WEIGHTS.items() if components[k] is not None}
    weight_sum = sum(active_weights.values())

    composite = sum(
        components[k] * (weight / weight_sum) # type: ignore
        for k, weight in active_weights.items()
    )

    return {
        "score": round(composite, 2),
        "components": components,
        "skill_level": skill_level,
        "wave_height_m": wave_height_m,
        "wave_period_s": wave_period_s,
        "wind_speed_kt": wind_speed_kt,
        "wind_direction_deg": wind_direction_deg,
        "wave_direction_deg": wave_direction_deg,
    }


def score_week(
    forecast: dict, spot: dict, skill_level: str = _DEFAULT_SKILL_LEVEL
) -> list[dict[str, Any]]:
    """Evaluates every hour in a forecast payload for a target spot."""
    rows = forecast.get("hourly", [])
    results = []

    for row in rows:
        wave_height = row.get("wave_height")
        wave_period = row.get("wave_period")
        wind_speed = row.get("wind_speed_10m")
        wind_dir = row.get("wind_direction_10m")

        if None in (wave_height, wave_period, wind_speed, wind_dir):
            continue

        scored = score_hour(
            wave_height_m=float(wave_height),
            wave_period_s=float(wave_period),
            wind_speed_kt=float(wind_speed) * 0.539957,  # km/h to knots conversion
            wind_direction_deg=float(wind_dir),
            spot=spot,
            wave_direction_deg=float(row["wave_direction"]) if row.get("wave_direction") is not None else None,
            skill_level=skill_level,
        )
        scored["time"] = row["time"]
        results.append(scored)

    return results


def rank_spots_this_week(
    forecasts: dict[tuple[str, str], dict],
    spots_list: list[dict],
    skill_level: str = _DEFAULT_SKILL_LEVEL,
) -> list[dict[str, Any]]:
    """Ranks provided spots by their maximum achievable hourly score."""
    ranked = []

    for spot in spots_list:
        key = (spot["name"], spot["region"])
        if key not in forecasts:
            continue

        hours = score_week(forecasts[key], spot, skill_level=skill_level)
        best_hour = max(hours, key=lambda h: h["score"]) if hours else None

        ranked.append(
            {
                "name": spot["name"],
                "region": spot["region"],
                "skill_level": skill_level,
                "best_score": best_hour["score"] if best_hour else 0.0,
                "best_time": best_hour["time"] if best_hour else None,
                "best_hour": best_hour,
            }
        )

    ranked.sort(key=lambda x: x["best_score"], reverse=True)
    return ranked
