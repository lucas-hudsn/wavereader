"""Deterministic surf-quality scoring engine, v2 (wavereader core port).

Merges ``app/adapters.py`` (break-record → spot shaping) with
``app/scoring.py`` (skill-calibrated Gaussian component curves).

Scoring v2 upgrades over the v1 port:

* **Swell components first** — :func:`score_week` prefers
  ``swell_wave_height`` / ``swell_wave_direction`` / ``swell_wave_period``
  when the frame carries them, falling back to the generic ``wave_*``
  aggregates otherwise.
* **Direction arc, not cyclic mean** — the ideal direction list is parsed
  to a *set* of bearings (:func:`_ideal_bearings`) and the score uses the
  minimum angular distance to *any* of them. A break that takes both E
  and S no longer scores its middle (SE-ish mean) as perfect.
* **Wind cap from ``idealWind.type``** — offshore 18 kt, cross-shore 12,
  onshore 8, light/variable 10 — with a smooth logistic roll-off centred
  at the cap instead of the old 10→0 cliff. The effective cap is still
  bounded above by the skill profile's ``max_wind_kt``.
* **Daylight-only** — :func:`score_week` drops night hours using
  ``daily.sunrise``/``sunset`` from the forecast frame
  (``daylight_only=False`` restores all hours).
* **Daily summary = p75** — :func:`daily_summary` reports the 75th
  percentile of daylight scores per date (consistency over one lucky
  hour).
* **Rank by surfable hours** — :func:`rank_spots` orders by
  (hours with score ≥ 6, then best score).

Stable public signatures (Worker C builds against these)::

    score_week(forecast, spot, skill_level="intermediate", daylight_only=True)
    rank_spots(forecasts, spots_list, skill_level="intermediate")

Deterministic only: no LLM, no network.
"""

from __future__ import annotations

import math
from typing import Any, Optional

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

# Wind caps (kt) by ideal-wind type. Break type is carried on the spot
# dict for downstream use; the cap itself is driven by wind type.
_WIND_CAP_BY_TYPE: dict[str, float] = {
    "offshore": 18.0,
    "cross-shore": 12.0,
    "onshore": 8.0,
    "light/variable": 10.0,
}
# Logistic steepness (kt): score falls from ~9.5 to ~0.5 over ±3 kt
# around the cap.
_WIND_LOGISTIC_STEEPNESS = 1.0

SURFABLE_THRESHOLD = 6.0

DEFAULT_DIRECTION = "E"

_SCORING_SKILLS = frozenset({"beginner", "intermediate", "advanced", "expert"})
_FALLBACK_SKILL = "intermediate"


# ---- Adapter shaping (ported from app/adapters.py) ----

def normalize_skill(skill: str | None) -> str:
    """Normalise an enriched ``skillLevel`` to a scoring skill tier."""
    if skill is None:
        return _FALLBACK_SKILL
    s = str(skill).strip().lower()
    if s in ("pro-only", "pro only", "pro"):
        return "expert"
    if s in _SCORING_SKILLS:
        return s
    return _FALLBACK_SKILL


def _join_direction(directions) -> str:
    """Join a compass-point list with ``/``; default to ``"E"`` when empty."""
    if not directions:
        return DEFAULT_DIRECTION
    if isinstance(directions, str):
        text = directions.strip()
        return text if text else DEFAULT_DIRECTION
    parts = [str(d).strip() for d in directions if str(d).strip()]
    return "/".join(parts) if parts else DEFAULT_DIRECTION


def _normalize_wind_type(wind_type: str | None) -> str:
    """Normalise an enriched ``idealWind.type`` to a wind-cap key."""
    t = str(wind_type or "").strip().lower()
    if "cross" in t:
        return "cross-shore"
    if "onshore" in t or t == "on":
        return "onshore"
    if "offshore" in t or t == "off":
        return "offshore"
    if "light" in t or "variable" in t:
        return "light/variable"
    return "light/variable"


def _safe_float(value) -> float | None:
    """Coerce to finite float, else None (rejects None/NaN/garbage)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def enriched_to_scoring_spot(break_: dict) -> dict:
    """Convert one enriched break record to the scoring spot shape.

    v2: carries ``ideal_wind.type`` (drives the wind cap) and
    ``break_type`` through; the legacy flat ``strength_kt_max`` is gone.
    """
    swell = break_.get("idealSwell", {}) or {}
    size = swell.get("sizeRangeFt", {}) or {}
    wind = break_.get("idealWind", {}) or {}
    size_min = _safe_float(size.get("min", 0.0))
    size_max = _safe_float(size.get("max", 0.0))
    return {
        "name": break_.get("name", ""),
        "region": break_.get("region", ""),
        "break_type": break_.get("breakType", ""),
        "ideal_swell": {
            "direction": _join_direction(swell.get("direction")),
            "size_ft_min": size_min if size_min is not None else 0.0,
            "size_ft_max": size_max if size_max is not None else 0.0,
        },
        "ideal_wind": {
            "direction": _join_direction(wind.get("direction")),
            "type": _normalize_wind_type(wind.get("type")),
        },
    }


def get_coords(break_: dict) -> tuple[float | None, float | None]:
    """Return ``(lat, lng)`` (None on missing coords)."""
    try:
        lat = float(break_["location"]["coordinates"]["lat"])
    except (KeyError, TypeError, ValueError):
        lat = None
    try:
        lng = float(break_["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        lng = None
    return lat, lng


def break_skill(break_: dict) -> str:
    """Return the normalised skill tier for an enriched break record."""
    return normalize_skill(break_.get("skillLevel"))


def wind_cap(spot: dict, skill_level: str = _DEFAULT_SKILL_LEVEL) -> float:
    """Effective wind cap (kt) for a spot + skill tier.

    Base cap from ``ideal_wind.type`` (offshore 18 / cross-shore 12 /
    onshore 8 / light-variable 10), bounded above by the skill profile's
    ``max_wind_kt``.
    """
    wind = spot.get("ideal_wind", {}) or {}
    base = _WIND_CAP_BY_TYPE.get(
        _normalize_wind_type(wind.get("type")), _WIND_CAP_BY_TYPE["light/variable"]
    )
    try:
        profile_max = float(_SKILL_PROFILES[skill_level]["max_wind_kt"])
    except (KeyError, TypeError, ValueError):
        return base
    return min(base, profile_max)


# ---- Direction helpers ----

def _ideal_bearings(direction: str) -> list[float]:
    """Parse a slash-separated ideal-direction string to a set of bearings.

    Accepts the ``"SW/S/SSW"`` shape produced by :func:`_join_direction`
    (also tolerates commas and " to " separators). Unknown tokens are
    ignored; raises ``ValueError`` when nothing parses.
    """
    normalized = (
        direction.replace(",", "/").replace(" to ", "/").replace(" ", "").upper()
    )
    degs = [_COMPASS_DEG[p] for p in normalized.split("/") if p in _COMPASS_DEG]
    if not degs:
        raise ValueError(f"Invalid compass direction input: {direction!r}")
    # Dedupe while preserving order.
    seen: set[float] = set()
    out: list[float] = []
    for d in degs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def _dir_to_deg(direction: str) -> float:
    """Mean bearing of a slash-separated direction string (legacy helper).

    Kept for compatibility; scoring v2 uses :func:`_ideal_bearings` (arc
    distance to the nearest ideal bearing) instead of the cyclic mean.
    """
    degs = _ideal_bearings(direction)
    sin_sum = sum(math.sin(math.radians(d)) for d in degs)
    cos_sum = sum(math.cos(math.radians(d)) for d in degs)
    mean_deg = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
    return round(mean_deg, 1)


def _angular_diff(a: float, b: float) -> float:
    """Shortest arc distance between two bearings in degrees."""
    d = abs(a - b) % 360.0
    return d if d <= 180.0 else 360.0 - d


def _arc_distance(wave_dir_deg: float, ideal_direction: str) -> float:
    """Minimum angular distance from a bearing to the ideal-direction arc."""
    return min(_angular_diff(wave_dir_deg, b) for b in _ideal_bearings(ideal_direction))


def _gaussian_decay(value: float, target: float, sigma: float) -> float:
    """Smooth Gaussian decay yielding 1.0 at target and trailing to 0.0."""
    return math.exp(-((value - target) ** 2) / (2 * (sigma ** 2)))


def _logistic_wind_speed_score(wind_speed_kt: float, cap_kt: float) -> float:
    """Smooth 0–10 speed score: ~10 well below cap, 5.0 at cap, ~0 above."""
    return 10.0 / (1.0 + math.exp((wind_speed_kt - cap_kt) / _WIND_LOGISTIC_STEEPNESS))


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
    """Directional match = Gaussian falloff from the *nearest* ideal bearing.

    v2 replaces the cyclic mean: a break ideal at ``"E/SE"`` scores 10.0
    at exactly E *or* SE, instead of peaking at the ESE midpoint.
    """
    diff = _arc_distance(wave_dir_deg, spot["ideal_swell"]["direction"])

    # Half-width tolerance angle before severe drop-off (e.g., 45 degrees)
    tolerance_deg = 45.0
    score = 10.0 * _gaussian_decay(diff, 0.0, tolerance_deg / 1.5)
    return max(0.0, min(10.0, score))


def _score_wind(
    wind_speed_kt: float,
    wind_dir_deg: float,
    spot: dict,
    skill_level: str = _DEFAULT_SKILL_LEVEL,
    gust_kt: float | None = None,
) -> float:
    """Scores wind as the mean of a speed score and a direction score.

    Speed: logistic roll-off centred at the effective cap
    (:func:`wind_cap` — wind type table bounded by the skill profile),
    so glassy air scores ~10 and howling air scores ~0 with no cliff.
    Direction: cosine falloff from the nearest ideal (offshore) bearing
    to absolute onshore. Gusts (optional, kt): gust > limit+10 knocks
    2 points off, gust > limit+5 knocks 1 point off — same limit, no new
    thresholds.
    """
    limit = wind_cap(spot, skill_level)

    offshore_arc = spot["ideal_wind"]["direction"]
    diff = _arc_distance(wind_dir_deg, offshore_arc)
    dir_score = 10.0 * max(0.0, math.cos(math.radians(diff / 2.0)))

    speed_score = _logistic_wind_speed_score(wind_speed_kt, limit)

    base = round((speed_score + dir_score) / 2.0, 2)
    if gust_kt is not None:
        try:
            gust = float(gust_kt)
        except (TypeError, ValueError):
            gust = None
        if gust is not None:
            if gust > limit + 10:
                base = max(0.0, round(base - 2.0, 2))
            elif gust > limit + 5:
                base = max(0.0, round(base - 1.0, 2))
    return base


def _score_period(period_s: float, skill_level: str = _DEFAULT_SKILL_LEVEL) -> float:
    """Evaluates swell period quality: 0 below 4 s, 10 from 14 s up.

    Long groundswell is never penalised for experienced surfers — there
    is no falloff above 14 s. Beginners get a gentle cap above their
    ``ideal_period_max_s`` (12 s): very long-period power is harder to
    handle, so the score eases down to a floor of ~5 instead of 10.
    """
    if period_s <= 4.0:
        return 0.0
    if period_s >= 14.0:
        base = 10.0
    else:
        base = round(10.0 * (period_s - 4.0) / 10.0, 2)
    try:
        ideal_max = float(_SKILL_PROFILES[skill_level]["ideal_period_max_s"])
    except (KeyError, TypeError, ValueError):
        return base
    if skill_level == "beginner" and period_s > ideal_max:
        base = max(5.0, round(base - (period_s - ideal_max) * 0.4, 2))
    return base


# ---- Daylight filtering ----

def _daylight_windows(daily: dict | None) -> dict[str, tuple[str, str]]:
    """Map ``date → (sunrise_hhmm, sunset_hhmm)`` from a daily sun frame."""
    out: dict[str, tuple[str, str]] = {}
    if not isinstance(daily, dict):
        return out
    times = daily.get("time") or []
    rises = daily.get("sunrise") or []
    sets = daily.get("sunset") or []
    for i, day in enumerate(times):
        try:
            rise, set_ = rises[i], sets[i]
        except IndexError:
            continue
        if not (isinstance(rise, str) and isinstance(set_, str)):
            continue
        # ISO local "YYYY-MM-DDTHH:MM" — require full length, else skip
        # (a truncated sun string must not nuke the whole date).
        if len(rise) < 16 or len(set_) < 16:
            continue
        # ISO local "YYYY-MM-DDTHH:MM" — compare the HH:MM slice.
        out[str(day)[:10]] = (rise[11:16], set_[11:16])
    return out


def is_daylight(iso_time: str, windows: dict[str, tuple[str, str]]) -> bool:
    """True when an hourly ISO timestamp falls between sunrise and sunset."""
    day = str(iso_time)[:10]
    window = windows.get(day)
    if window is None:
        return True  # fail-open when the frame carries no sun times
    rise, set_ = window
    hhmm = str(iso_time)[11:16]
    return rise <= hhmm <= set_


# ---- Main Interface Functions ----

def score_hour(
    wave_height_m: float,
    wave_period_s: float,
    wind_speed_kt: float,
    wind_direction_deg: float,
    spot: dict,
    wave_direction_deg: Optional[float] = None,
    skill_level: str = _DEFAULT_SKILL_LEVEL,
    gust_kt: Optional[float] = None,
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
    c_wind = _score_wind(wind_speed_kt, wind_direction_deg, spot, skill_level, gust_kt=gust_kt)
    c_period = _score_period(wave_period_s, skill_level)

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
        components[k] * (weight / weight_sum)  # type: ignore
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
        "gust_kt": gust_kt,
    }


def _pick_height(row: dict) -> float | None:
    """Prefer the swell component; fall back to the generic aggregate."""
    for key in ("swell_wave_height", "wave_height"):
        v = row.get(key)
        f = _safe_float(v) if v is not None else None
        if f is not None:
            return f
    return None


def _pick_direction(row: dict) -> float | None:
    """Prefer the swell direction; fall back to the generic aggregate."""
    for key in ("swell_wave_direction", "wave_direction"):
        v = row.get(key)
        f = _safe_float(v) if v is not None else None
        if f is not None:
            return f
    return None


def _pick_period(row: dict) -> float | None:
    """Prefer the swell period; fall back to the generic aggregate."""
    for key in ("swell_wave_period", "wave_period"):
        v = row.get(key)
        f = _safe_float(v) if v is not None else None
        if f is not None:
            return f
    return None


def score_week(
    forecast: dict, spot: dict, skill_level: str = _DEFAULT_SKILL_LEVEL,
    daylight_only: bool = True,
) -> list[dict[str, Any]]:
    """Score every (daylight) hour in a forecast frame for a target spot.

    ``daylight_only=True`` (default) drops night hours using
    ``forecast["daily"]`` sunrise/sunset; pass ``False`` to score every
    hour. Each returned hour carries its ``"time"``. Hours missing any
    required field are skipped.
    """
    rows = forecast.get("hourly", []) if isinstance(forecast, dict) else []
    if not isinstance(rows, list):
        return []
    windows = _daylight_windows(forecast.get("daily")) if daylight_only else {}
    results = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        t = row.get("time")
        if not isinstance(t, str) or not t:
            continue
        if daylight_only and not is_daylight(t, windows):
            continue
        wave_height = _pick_height(row)
        wave_period = _pick_period(row)
        wind_speed = _safe_float(row.get("wind_speed_10m"))
        wind_dir = _safe_float(row.get("wind_direction_10m"))

        if None in (wave_height, wave_period, wind_speed, wind_dir):
            continue

        gust_kt = _safe_float(row.get("wind_gusts_10m"))
        if gust_kt is not None:
            gust_kt = gust_kt * 0.539957

        try:
            scored = score_hour(
                wave_height_m=float(wave_height),
                wave_period_s=float(wave_period),
                wind_speed_kt=float(wind_speed) * 0.539957,  # km/h to knots conversion
                wind_direction_deg=float(wind_dir),
                spot=spot,
                wave_direction_deg=_pick_direction(row),
                skill_level=skill_level,
                gust_kt=gust_kt,
            )
        except (ValueError, TypeError, KeyError):
            # One bad spot field or hour must not abort the whole week.
            continue
        scored["time"] = t
        results.append(scored)

    return results


def _percentile(xs: list[float], q: float) -> float:
    """Linear-interpolation percentile (q in 0..1) over a non-empty list."""
    s = sorted(xs)
    if len(s) == 1:
        return float(s[0])
    rank = q * (len(s) - 1)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return float(s[lo])
    frac = rank - lo
    return float(s[lo] * (1 - frac) + s[hi] * frac)


def daily_summary(scored_hours: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-date summary of scored hours: p75 score (consistency signal).

    Returns ``[{"date", "p75", "best", "n", "surfable_hours"}]`` sorted by
    date, where ``surfable_hours`` counts hours with score ≥ 6.
    """
    by_date: dict[str, list[float]] = {}
    for h in scored_hours:
        if not isinstance(h, dict):
            continue
        t = h.get("time")
        if not isinstance(t, str):
            continue
        try:
            score = float(h["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue
        by_date.setdefault(t[:10], []).append(score)

    out = []
    for date in sorted(by_date):
        scores = by_date[date]
        out.append(
            {
                "date": date,
                "p75": round(_percentile(scores, 0.75), 2),
                "best": round(max(scores), 2),
                "n": len(scores),
                "surfable_hours": sum(1 for s in scores if s >= SURFABLE_THRESHOLD),
            }
        )
    return out


def rank_spots(
    forecasts: dict[tuple[str, str], dict],
    spots_list: list[dict],
    skill_level: str = _DEFAULT_SKILL_LEVEL,
) -> list[dict[str, Any]]:
    """Rank spots by (surfable hours with score ≥ 6, then best score).

    ``forecasts`` maps ``(name, region)`` → forecast frame. Spots with no
    frame are skipped. Ties on surfable hours break toward the higher
    single-hour best.
    """
    ranked = []

    for spot in spots_list:
        key = (spot["name"], spot["region"])
        if key not in forecasts:
            continue

        hours = score_week(forecasts[key], spot, skill_level=skill_level)
        best_hour = max(hours, key=lambda h: h["score"]) if hours else None
        surfable = sum(1 for h in hours if h["score"] >= SURFABLE_THRESHOLD)

        ranked.append(
            {
                "name": spot["name"],
                "region": spot["region"],
                "skill_level": skill_level,
                "surfable_hours": surfable,
                "total_hours": len(hours),
                "best_score": best_hour["score"] if best_hour else 0.0,
                "best_time": best_hour["time"] if best_hour else None,
                "best_hour": best_hour,
            }
        )

    ranked.sort(key=lambda x: (x["surfable_hours"], x["best_score"]), reverse=True)
    return ranked


# Backwards-compatible alias for the v1 entry point name.
def rank_spots_this_week(
    forecasts: dict[tuple[str, str], dict],
    spots_list: list[dict],
    skill_level: str = _DEFAULT_SKILL_LEVEL,
) -> list[dict[str, Any]]:
    """Alias of :func:`rank_spots` (v1 name)."""
    return rank_spots(forecasts, spots_list, skill_level=skill_level)


__all__ = [
    "SKILL_LEVELS",
    "SURFABLE_THRESHOLD",
    "DEFAULT_DIRECTION",
    "normalize_skill",
    "enriched_to_scoring_spot",
    "get_coords",
    "break_skill",
    "wind_cap",
    "is_daylight",
    "score_hour",
    "score_week",
    "daily_summary",
    "rank_spots",
    "rank_spots_this_week",
]
