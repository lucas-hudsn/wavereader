"""Deterministic surf-quality scoring.

The LLM never owns numbers: every score and ranking comes from here.
Produces a 0-10 quality score per hour plus a component breakdown
(swell size vs ideal, swell direction match, wind speed + offshore
alignment, wave period). Tide is qualitative only — Open-Meteo has no
tides, so it never feeds the numeric score.
"""

from __future__ import annotations

import math

# ---- 16-point compass → degrees (midpoint) ----

_COMPASS_DEG: dict[str, float] = {
    "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
    "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
    "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
    "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
}

# Weights for the four components → sum to 1.0
_WEIGHTS = {
    "swell_size": 0.25,
    "swell_direction": 0.20,
    "wind": 0.30,
    "period": 0.25,
}


def _dir_to_deg(direction: str) -> float:
    """Parse a cardinal direction string to degrees.

    Handles single compass points ('SW'), compound ranges ('W/SW'),
    and comma-separated values ('SE, S, E') by averaging the endpoints.
    """
    # Normalize separators: replace commas with slashes
    direction = direction.replace(",", "/")
    parts = direction.replace(" ", "").split("/")
    degs = [_COMPASS_DEG[p] for p in parts]
    return sum(degs) / len(degs)


def _angular_diff(a: float, b: float) -> float:
    """Shortest angular distance between two bearings in degrees."""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def _score_swell_size(wave_height_m: float, spot: dict) -> float:
    """Score 0-10 based on how close wave_height_m is to the ideal range.

    Ideal size is stored in feet; convert to metres for comparison.
    Perfect score (10) inside the range, linear decay to 0 at ±30 % outside.
    """
    ideal = spot["ideal_swell"]
    min_m = ideal["size_ft_min"] * 0.3048
    max_m = ideal["size_ft_max"] * 0.3048

    margin = max(max_m - min_m, 0.1)
    low_cutoff = min_m - margin
    high_cutoff = max_m + margin

    if low_cutoff <= wave_height_m <= high_cutoff:
        if min_m <= wave_height_m <= max_m:
            return 10.0
        # Partial credit inside the extended range
        if wave_height_m < min_m:
            return 10.0 - 10.0 * (min_m - wave_height_m) / margin
        return 10.0 - 10.0 * (wave_height_m - max_m) / margin

    return max(
        10.0 * (1.0 - (low_cutoff - wave_height_m) / margin)
        if wave_height_m < low_cutoff
        else 10.0 * (1.0 - (wave_height_m - high_cutoff) / margin),
        0.0,
    )


def _score_swell_direction(wave_dir_deg: float, spot: dict) -> float:
    """Score 0-10 based on angular match between wave direction and ideal.

    0° difference → 10; 90° → ~3; 180° → 0.
    """
    ideal_deg = _dir_to_deg(spot["ideal_swell"]["direction"])
    diff = _angular_diff(wave_dir_deg, ideal_deg)
    return max(0.0, 10.0 - (diff / 180.0) * 10.0)


def _score_wind(wind_speed_kt: float, wind_dir_deg: float, spot: dict) -> float:
    """Score 0-10 combining wind-speed favour and direction (offshore) alignment.

    Offshore wind (matching the ideal direction) is best.
    Speed score peaks at ~50 % of strength_kt_max and falls to 0 at max.
    Direction score follows the same angular model as swell direction.
    """
    ideal = spot["ideal_wind"]
    ideal_dir_deg = _dir_to_deg(ideal["direction"])

    # Speed: 10 at ≤ half max, linear to 0 at max
    speed_score = max(0.0, 10.0 - 10.0 * wind_speed_kt / ideal["strength_kt_max"])
    speed_score = min(speed_score, 10.0)

    # Direction: angular difference from ideal offshore direction
    dir_diff = _angular_diff(wind_dir_deg, ideal_dir_deg)
    dir_score = max(0.0, 10.0 - (dir_diff / 180.0) * 10.0)

    return speed_score * 0.5 + dir_score * 0.5


def _score_period(period_s: float) -> float:
    """Score 0-10 for wave period.

    Longer periods = better quality. 8 s → ~6, 10 s → 8, 14 s+ → 10,
    falling off after ~16 s.
    """
    if period_s >= 14.0:
        return 10.0
    if period_s <= 4.0:
        return 0.0
    if period_s >= 10.0:
        # smooth ramp 10→14
        return 8.0 + 2.0 * (period_s - 10.0) / 4.0
    # ramp 4→10
    return 6.0 * (period_s - 4.0) / 6.0


def score_hour(
    wave_height_m: float,
    wave_period_s: float,
    wind_speed_kt: float,
    wind_direction_deg: float,
    spot: dict,
) -> dict:
    """Score one hour against a spot's ideal profile.

    Returns a dict with the composite 0-10 ``score``, a per-component
    ``components`` breakdown, and the raw inputs for the UI.
    """
    c_size = _score_swell_size(wave_height_m, spot)
    c_dir = _score_swell_direction(wind_direction_deg, spot)
    c_wind = _score_wind(wind_speed_kt, wind_direction_deg, spot)
    c_period = _score_period(wave_period_s)

    total = (
        c_size * _WEIGHTS["swell_size"]
        + c_dir * _WEIGHTS["swell_direction"]
        + c_wind * _WEIGHTS["wind"]
        + c_period * _WEIGHTS["period"]
    )

    return {
        "score": round(total, 2),
        "components": {
            "swell_size": round(c_size, 2),
            "swell_direction": round(c_dir, 2),
            "wind": round(c_wind, 2),
            "period": round(c_period, 2),
        },
        "wave_height_m": wave_height_m,
        "wave_period_s": wave_period_s,
        "wind_speed_kt": wind_speed_kt,
        "wind_direction_deg": wind_direction_deg,
    }


def score_week(forecast: dict, spot: dict) -> list[dict]:
    """Score every hour of a 7-day forecast for one spot.

    ``forecast`` is the normalised ``{"hourly": [...]}`` frame from
    ``forecasts.py``.  Each hour row must carry ``time``,
    ``wave_height``, ``wave_period``, ``wind_speed_10m`` and
    ``wind_direction_10m``.
    """
    rows = forecast["hourly"]
    results: list[dict] = []
    for row in rows:
        scored = score_hour(
            wave_height_m=float(row["wave_height"]),
            wave_period_s=float(row["wave_period"]),
            wind_speed_kt=float(row["wind_speed_10m"]) * 0.539957,  # km/h → kt
            wind_direction_deg=float(row["wind_direction_10m"]),
            spot=spot,
        )
        scored["time"] = row["time"]
        results.append(scored)
    return results


def rank_spots_this_week(forecasts: dict, spots_list: list[dict]) -> list[dict]:
    """Rank spots by their best single-hour score across the week.

    ``forecasts`` maps ``(name, region)`` → normalised forecast frame.
    Returns entries sorted by best score descending.
    """
    ranked: list[dict] = []
    for spot in spots_list:
        key = (spot["name"], spot["region"])
        if key not in forecasts:
            continue
        hours = score_week(forecasts[key], spot)
        best = max(hours, key=lambda h: h["score"]) if hours else None
        ranked.append({
            "name": spot["name"],
            "region": spot["region"],
            "best_score": best["score"] if best else 0.0,
            "best_time": best["time"] if best else None,
            "best_hour": best,
        })
    ranked.sort(key=lambda x: x["best_score"], reverse=True)
    return ranked
