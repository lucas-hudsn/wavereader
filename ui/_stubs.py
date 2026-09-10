"""Minimal local stand-ins for Worker A/C modules (NOT the real core).

Workers A/C own ``wavereader/*`` on parallel branches; those modules do not
exist on this branch yet. This module provides deterministic fakes with the
same *shapes* the real tools will return, so the UI builds and renders
offline today.

MERGE REWIRING (orchestrator): ``ui/_compat.py`` already tries the real
``wavereader.*`` imports first — once Worker A/C merge, the stubs stop being
used with no UI changes. Delete this module only when ``wavereader/tools.py``
+ ``wavereader/climate.py`` + ``wavereader/seafloor.py`` are all merged.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

SKILL_ORDER = ["beginner", "intermediate", "advanced", "expert", "pro-only"]

STUB_BREAKS: list[dict] = [
    {
        "id": "stub-bells-beach",
        "name": "Bells Beach",
        "state": "Victoria",
        "region": "Surf Coast",
        "description": "Famous right-hand reef break (stub record for UI development).",
        "skillLevel": "intermediate",
        "breakType": "reef",
        "peakType": "right",
        "location": {"country": "Australia", "state": "Victoria", "region": "Surf Coast",
                     "coordinates": {"lat": -38.3667, "lng": 144.2833}},
        "idealSwell": {"direction": ["SW", "S"], "sizeRangeFt": {"min": 3, "max": 8}},
        "idealWind": {"direction": ["N", "NW"], "type": "offshore"},
        "idealTide": {"stage": ["mid", "high"]},
        "bestSeason": ["autumn", "winter"],
        "hazards": ["rocks", "crowd"],
        "crowdFactor": "high",
    },
    {
        "id": "stub-snapper-rocks",
        "name": "Snapper Rocks",
        "state": "Queensland",
        "region": "Gold Coast",
        "description": "Superbank sand point, long right (stub record).",
        "skillLevel": "advanced",
        "breakType": "sand",
        "peakType": "right",
        "location": {"country": "Australia", "state": "Queensland", "region": "Gold Coast",
                     "coordinates": {"lat": -28.1656, "lng": 153.5500}},
        "idealSwell": {"direction": ["E", "SE"], "sizeRangeFt": {"min": 2, "max": 6}},
        "idealWind": {"direction": ["SW", "S"], "type": "offshore"},
        "idealTide": {"stage": ["mid"]},
        "bestSeason": ["autumn", "winter"],
        "hazards": ["crowd", "rocks"],
        "crowdFactor": "high",
    },
    {
        "id": "stub-noosa-heads",
        "name": "Noosa Heads",
        "state": "Queensland",
        "region": "Sunshine Coast",
        "description": "Gentle right points, beginner friendly (stub record).",
        "skillLevel": "beginner",
        "breakType": "point",
        "peakType": "right",
        "location": {"country": "Australia", "state": "Queensland", "region": "Sunshine Coast",
                     "coordinates": {"lat": -26.3833, "lng": 153.1000}},
        "idealSwell": {"direction": ["N", "NE"], "sizeRangeFt": {"min": 1, "max": 4}},
        "idealWind": {"direction": ["SW"], "type": "offshore"},
        "idealTide": {"stage": ["mid", "high"]},
        "bestSeason": ["summer", "autumn"],
        "hazards": ["crowd"],
        "crowdFactor": "high",
    },
    {
        "id": "stub-the-pass",
        "name": "The Pass",
        "state": "New South Wales",
        "region": "Byron",
        "description": "Mellow sand point at Byron Bay (stub record).",
        "skillLevel": "beginner",
        "breakType": "sand",
        "peakType": "right",
        "location": {"country": "Australia", "state": "New South Wales", "region": "Byron",
                     "coordinates": {"lat": -28.6333, "lng": 153.6333}},
        "idealSwell": {"direction": ["E", "NE"], "sizeRangeFt": {"min": 1, "max": 4}},
        "idealWind": {"direction": ["SW", "W"], "type": "offshore"},
        "idealTide": {"stage": ["mid"]},
        "bestSeason": ["autumn"],
        "hazards": ["crowd"],
        "crowdFactor": "high",
    },
    {
        "id": "stub-margaret-river",
        "name": "Margaret River Main Break",
        "state": "Western Australia",
        "region": "South West",
        "description": "Heavy reef, expert only (stub record).",
        "skillLevel": "expert",
        "breakType": "reef",
        "peakType": "a-frame",
        "location": {"country": "Australia", "state": "Western Australia",
                     "region": "South West",
                     "coordinates": {"lat": -33.9500, "lng": 114.9833}},
        "idealSwell": {"direction": ["SW", "W"], "sizeRangeFt": {"min": 4, "max": 12}},
        "idealWind": {"direction": ["E", "NE"], "type": "offshore"},
        "idealTide": {"stage": ["mid"]},
        "bestSeason": ["winter"],
        "hazards": ["rocks", "shallow reef", "sharks"],
        "crowdFactor": "medium",
    },
    {
        "id": "stub-bondi",
        "name": "Bondi Beach",
        "state": "New South Wales",
        "region": "Sydney",
        "description": "City beach break, peaks up and down the beach (stub record).",
        "skillLevel": "beginner",
        "breakType": "beach",
        "peakType": "a-frame",
        "location": {"country": "Australia", "state": "New South Wales", "region": "Sydney",
                     "coordinates": {"lat": -33.8915, "lng": 151.2767}},
        "idealSwell": {"direction": ["S", "SE"], "sizeRangeFt": {"min": 1, "max": 4}},
        "idealWind": {"direction": ["W", "NW"], "type": "offshore"},
        "idealTide": {"stage": ["low", "mid"]},
        "bestSeason": ["summer", "autumn"],
        "hazards": ["crowd", "rips"],
        "crowdFactor": "high",
    },
]

_DIRECTIONS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _rng01(key: str) -> float:
    h = hashlib.md5(key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def _ideal_mid(break_: dict) -> float:
    size = ((break_ or {}).get("idealSwell") or {}).get("sizeRangeFt") or {}
    try:
        return (float(size.get("min", 1)) + float(size.get("max", 4))) / 2.0
    except (TypeError, ValueError):
        return 2.5


def stub_scored_hours(break_: dict, skill: str = "intermediate",
                      days: int = 3) -> list[dict]:
    """Deterministic fake scored hours (06:00–17:00 local, 12/day).

    Shape matches the real ``score_week`` hour rows: ``time, score,
    wave_height_m, wave_period_s, wind_speed_kt, wind_direction_deg``.
    """
    name = (break_ or {}).get("name", "?")
    mid = _ideal_mid(break_)
    hours: list[dict] = []
    today = date(2026, 9, 9)
    for d in range(max(1, min(7, int(days)))):
        day = today + timedelta(days=d + 1)
        for h in range(6, 18):
            key = f"{name}|{day.isoformat()}|{h}"
            swell = mid + 1.1 * math.sin(d * 1.3 + h * 0.35) + (_rng01(key + "h") - 0.5) * 1.6
            swell = max(0.3, round(swell, 1))
            period = round(6 + 7 * _rng01(key + "p") + 0.8 * math.sin(h), 1)
            wind = round(max(0.0, 8 + 14 * _rng01(key + "w") - 6 * math.sin(h * 0.5)), 1)
            wdir = int(_rng01(key + "d") * 360) % 360
            # Plausible v1-style score: size closeness, wind penalty, period bonus.
            size_score = max(0.0, 10 - abs(swell - mid) * 2.2)
            wind_score = max(0.0, 10 - max(0.0, wind - 5) * 0.7)
            period_score = min(10.0, max(0.0, (period - 4) * 1.1))
            score = round(min(10.0, max(0.0, 0.4 * size_score + 0.35 * wind_score + 0.25 * period_score)), 1)
            hours.append(
                {
                    "time": f"{day.isoformat()}T{h:02d}:00",
                    "score": score,
                    "wave_height_m": swell,
                    "wave_period_s": period,
                    "wind_speed_kt": wind,
                    "wind_direction_deg": float(wdir),
                }
            )
    return hours


def _best(hours: list[dict]) -> dict | None:
    return max(hours, key=lambda r: r.get("score", 0)) if hours else None


def _daily_best(hours: list[dict]) -> list[dict]:
    best_by_date: dict[str, dict] = {}
    for row in hours:
        day = str(row.get("time", ""))[:10]
        if day and (day not in best_by_date or row.get("score", 0) > best_by_date[day].get("score", 0)):
            best_by_date[day] = row
    return [
        {"date": d, "time": r.get("time"), "score": r.get("score"),
         "wave_height_m": r.get("wave_height_m"), "wave_period_s": r.get("wave_period_s"),
         "wind_speed_kt": r.get("wind_speed_kt"), "wind_direction_deg": r.get("wind_direction_deg")}
        for d, r in sorted(best_by_date.items())
    ]


def find_stub(name: str) -> dict | None:
    """Find a stub break by name (case-insensitive)."""
    want = (name or "").strip().lower()
    for b in STUB_BREAKS:
        if b.get("name", "").strip().lower() == want:
            return b
    return None


def score_week(spot_name: str, region: str = "",
               skill: str = "intermediate") -> dict:
    """Fake ``score_week`` tool payload: spot/skill/scored/daily/best."""
    break_ = find_stub(spot_name) or dict(STUB_BREAKS[0])
    if region:
        break_ = dict(break_, region=region)
    hours = stub_scored_hours(break_, skill=skill, days=3)
    return {
        "spot": {"name": break_.get("name"), "region": break_.get("region")},
        "skill": skill,
        "scored": hours,
        "daily": _daily_best(hours),
        "best": _best(hours),
    }


def rank_region_week(region: str, skill: str = "intermediate") -> dict:
    """Fake ``rank_region_week`` payload: ``{"region", "rank": [rows]}``."""
    cands = [b for b in STUB_BREAKS if b.get("region", "").lower() == region.lower()] or STUB_BREAKS[:4]
    rows = []
    for b in cands:
        hours = stub_scored_hours(b, skill=skill, days=2)
        best = _best(hours) or {}
        rows.append(
            {
                "name": b.get("name"),
                "region": b.get("region"),
                "best_score": best.get("score"),
                "best_time": best.get("time"),
            }
        )
    rows.sort(key=lambda r: r.get("best_score") or 0, reverse=True)
    return {"region": region, "skill": skill, "rank": rows}


def explain_score(spot_name: str, skill: str = "intermediate", time: str = "") -> dict:
    """Fake ``explain_score`` payload: score + v1-style component breakdown."""
    payload = score_week(spot_name, skill=skill)
    hours = payload["scored"]
    row = next((h for h in hours if h.get("time") == time), None) or _best(hours) or {}
    score = float(row.get("score") or 0)
    return {
        "spot": payload["spot"],
        "skill": skill,
        "time": row.get("time"),
        "score": score,
        "components": {
            "size": round(min(10.0, score + 0.6), 1),
            "direction": round(min(10.0, score + 0.2), 1),
            "wind": round(max(0.0, score - 0.8), 1),
            "period": round(min(10.0, score + 0.4), 1),
        },
        "note": "stub breakdown (weights 30/20/30/20) — real engine lands with Worker A.",
    }


def climate_profile(break_: dict) -> dict:
    """Fake 5-year climate profile: 16-bin rose (%), best months, medians."""
    name = (break_ or {}).get("name", "?")
    raw = [_rng01(f"{name}|rose|{d}") + 0.15 for d in _DIRECTIONS_16]
    total = sum(raw)
    rose = {d: round(v / total * 100, 1) for d, v in zip(_DIRECTIONS_16, raw)}
    months = sorted(_MONTHS, key=lambda m: _rng01(f"{name}|month|{m}"), reverse=True)[:3]
    return {
        "rose": rose,
        "best_months": months,
        "median_height_m": round(0.6 + 2.4 * _rng01(f"{name}|h"), 1),
        "median_period_s": round(6 + 6 * _rng01(f"{name}|p"), 1),
    }


def seafloor_grid(break_: dict, radius_km: float = 1.2, n: int = 9) -> dict:
    """Fake bathymetry grid: depth increasing seaward + noise."""
    coords = ((break_ or {}).get("location") or {}).get("coordinates") or {}
    lat = float(coords.get("lat", -33.9))
    lng = float(coords.get("lng", 151.3))
    name = (break_ or {}).get("name", "?")
    half_lat = radius_km / 111.0
    half_lng = radius_km / max(20.0, 111.0 * math.cos(math.radians(lat)))
    lats = [round(lat + ((i / (n - 1)) * 2 - 1) * half_lat, 5) for i in range(n)]
    lngs = [round(lng + ((j / (n - 1)) * 2 - 1) * half_lng, 5) for j in range(n)]
    elev = []
    for i in range(n):
        for j in range(n):
            # Deeper to the east (seaward for east-coast stubs) + dip + noise.
            e = -2 - j * 2.2 - abs(i - n // 2) * 0.7 + (_rng01(f"{name}|sf|{i},{j}") - 0.5) * 3
            if j == 0 and i in (0, n - 1):
                e = abs(e) * 0.4  # land corners
            elev.append(round(e, 1))
    return {"lats": lats, "lngs": lngs, "elev": elev, "n": n,
            "radius_km": radius_km, "dataset": "stub-gebco",
            "center": {"lat": lat, "lng": lng}}
