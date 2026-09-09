"""THE 9 typed tool functions (Worker C — agent + narrator).

Single source for the smolagents ``ToolCallingAgent`` AND the Gradio MCP
surface (``@gr.api()``): every function carries the smolagents ``@tool``
decorator, a docstring with ``Args:``, and typed params/returns.

Deterministic-only contract: no LLM inside. Each tool wraps a Worker A
(scoring/forecasts/breaks/seafloor) or Worker B (climate) export. Those
modules do NOT exist yet on this branch, so every import is stubbed with a
``try/except`` + typed fake fallback returning plausible shapes (marked
``STUB(merge)``). At merge, delete the fallback and keep the import.

Agreed signatures coded against::

    score_week(forecast, spot, skill_level) -> list[dict]
    rank_spots(forecasts, spots, skill_level) -> list[dict]
    resolve_break(name, region) -> dict
    get_forecast(lat, lon, days) -> dict
    get_seafloor(lat, lng) -> dict{grid,analysis,stats}
    load_climate(slug) -> dict
    audit_break(break, climate) -> list[dict]
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from smolagents import tool

# ---------------------------------------------------------------------------
# STUB(merge): Worker A imports — rewire to wavereader/scoring.py etc. here.
# ---------------------------------------------------------------------------

try:  # Worker A: wavereader/scoring.py :: score_week(forecast, spot, skill_level)
    from wavereader.scoring import score_week as _core_score_week  # type: ignore
    _HAS_SCORING = True
except ImportError:
    _HAS_SCORING = False
    _core_score_week = None  # type: ignore

try:  # Worker A: wavereader/scoring.py :: rank_spots(forecasts, spots, skill_level)
    from wavereader.scoring import rank_spots as _core_rank_spots  # type: ignore
    _HAS_RANK = True
except ImportError:
    _HAS_RANK = False
    _core_rank_spots = None  # type: ignore

try:  # Worker A: wavereader/breaks.py :: resolve_break(name, region)
    from wavereader.breaks import resolve_break as _core_resolve_break  # type: ignore
    _HAS_BREAKS = True
except ImportError:
    _HAS_BREAKS = False
    _core_resolve_break = None  # type: ignore

try:  # Worker A: wavereader/openmeteo.py :: get_forecast(lat, lon, days)
    from wavereader.openmeteo import get_forecast as _core_get_forecast  # type: ignore
    _HAS_FORECAST = True
except ImportError:
    _HAS_FORECAST = False
    _core_get_forecast = None  # type: ignore

try:  # Worker A: wavereader/seafloor.py :: get_seafloor(lat, lng)
    from wavereader.seafloor import get_seafloor as _core_get_seafloor  # type: ignore
    _HAS_SEAFLOOR = True
except ImportError:
    _HAS_SEAFLOOR = False
    _core_get_seafloor = None  # type: ignore

# ---------------------------------------------------------------------------
# STUB(merge): Worker B imports — rewire to wavereader/climate.py here.
# ---------------------------------------------------------------------------

try:  # Worker B: wavereader/climate.py :: load_climate(slug)
    from wavereader.climate import load_climate as _core_load_climate  # type: ignore
    _HAS_CLIMATE = True
except ImportError:
    _HAS_CLIMATE = False
    _core_load_climate = None  # type: ignore

try:  # Worker B: wavereader/climate.py :: audit_break(break, climate)
    from wavereader.climate import audit_break as _core_audit_break  # type: ignore
    _HAS_AUDIT = True
except ImportError:
    _HAS_AUDIT = False
    _core_audit_break = None  # type: ignore

#: STUB(merge): exact stubbed imports needing rewire at merge time.
STUBBED_IMPORTS = (
    "wavereader.scoring.score_week",
    "wavereader.scoring.rank_spots",
    "wavereader.breaks.resolve_break",
    "wavereader.openmeteo.get_forecast",
    "wavereader.seafloor.get_seafloor",
    "wavereader.climate.load_climate",
    "wavereader.climate.audit_break",
)

# ---------------------------------------------------------------------------
# Local deterministic helpers (network-free; survive offline).
# ---------------------------------------------------------------------------

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "australia-surf-breaks-enriched.json"
_BREAKS_CACHE: list[dict] | None = None

_STATE_CODE_TO_NAME = {
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "VIC": "Victoria",
    "WA": "Western Australia",
    "SA": "South Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
}

_KNOWLEDGE_KEYS = (
    "name", "state", "region", "skillLevel", "breakType", "peakType",
    "idealSwell", "idealWind", "idealTide", "bestSeason", "hazards",
    "crowdFactor", "description", "location",
)
_SPOT_SUMMARY_KEYS = ("name", "state", "region", "skillLevel", "breakType", "peakType")

# STUB(merge): deterministic anchor so fake weeks are stable offline.
_FAKE_WEEK_ANCHOR = datetime(2026, 9, 7, 0, 0, 0)


def _load_breaks() -> list[dict]:
    """Load enriched records; tolerate missing file (offline-safe -> [])."""
    global _BREAKS_CACHE
    if _BREAKS_CACHE is not None:
        return _BREAKS_CACHE
    try:
        data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _BREAKS_CACHE = []
        return _BREAKS_CACHE
    records = list(data.values()) if isinstance(data, dict) else list(data)
    _BREAKS_CACHE = [r for r in records if isinstance(r, dict) and "error" not in r]
    return _BREAKS_CACHE


def _expand_state_code(value: str | None) -> str | None:
    if not value:
        return None
    return _STATE_CODE_TO_NAME.get(value.strip().upper())


def _region_matches(break_: dict, region: str) -> bool:
    want = region.strip().lower()
    expanded = _expand_state_code(region)
    candidates = {str(break_.get("state", "")).lower(), str(break_.get("region", "")).lower()}
    if want in candidates:
        return True
    return expanded is not None and expanded.lower() in candidates


def _resolve_local(name: str, region: Optional[str] = None) -> Optional[dict]:
    """Resolve a break: real ``wavereader.breaks`` first, local fallback.

    STUB(merge): the local substring branch below is the fallback that kept
    this module offline-capable before Worker A landed; keep it so dry-run
    tests never need the network/dataset beyond the local JSON file.
    """
    if _HAS_BREAKS and _core_resolve_break is not None:
        try:
            hit = _core_resolve_break(name, region)
        except Exception:
            hit = None
        if hit is not None:
            return hit
    if not (name or "").strip():
        return None
    want = name.strip().lower()
    breaks = _load_breaks()
    exact = [b for b in breaks if str(b.get("name", "")).lower() == want]
    candidates = exact or [b for b in breaks if want in str(b.get("name", "")).lower()]
    if not candidates:
        return None
    if region:
        for b in candidates:
            if _region_matches(b, region):
                return b
    return candidates[0]


def _coords(break_: dict) -> tuple[float | None, float | None]:
    """Extract (lat, lng) tolerating enriched + legacy coordinate shapes."""
    loc = (break_ or {}).get("location") or {}
    coords = loc.get("coordinates") or loc
    lat = coords.get("lat", coords.get("latitude", break_.get("lat")))
    lng = coords.get("lng", coords.get("lon", coords.get("longitude", break_.get("lng"))))
    try:
        return (float(lat), float(lng)) if lat is not None and lng is not None else (None, None)
    except (TypeError, ValueError):
        return (None, None)


def _real_scored(break_: dict, skill_level: str) -> list[dict]:
    """STUB(merge): fetch + score via Worker A; raises on any failure.

    Was the fake-data path before Worker A landed; now the primary path.
    """
    if not (_HAS_SCORING and _HAS_FORECAST and _core_score_week is not None and _core_get_forecast is not None):
        raise RuntimeError("scoring/forecast backends not available")
    lat, lng = _coords(break_)
    if lat is None or lng is None:
        raise RuntimeError(f"Spot '{break_.get('name')}' has no coordinates")
    forecast = _core_get_forecast(lat, lng, 7)
    spot = dict(break_)
    return _core_score_week(forecast, spot, skill_level)


def _scored_or_fake(break_: dict, skill_level: str) -> tuple[list[dict], bool]:
    """Real scored hours when backends work, else stable fake rows (offline)."""
    try:
        return _real_scored(break_, skill_level), False
    except Exception:
        return _fake_scored_week(str(break_.get("name"))), True


def _fake_score_for(name: str, hour_index: int) -> float:
    """STUB(merge): stable pseudo-score in [1, 9] so stubs look plausible."""
    digest = hashlib.sha256(f"{name}|{hour_index}".encode()).hexdigest()
    return round(1.0 + (int(digest[:4], 16) % 80) / 10.0, 1)


def _fake_scored_week(spot_name: str, n_hours: int = 24) -> list[dict]:
    """STUB(merge): plausible scored-hour rows until real scoring lands."""
    rows = []
    for i in range(n_hours):
        t = _FAKE_WEEK_ANCHOR + timedelta(hours=6 + i * 6)
        rows.append({
            "time": t.isoformat(),
            "score": _fake_score_for(spot_name, i),
            "wave_height_m": round(0.8 + (i % 5) * 0.3, 1),
            "wave_period_s": round(8.0 + (i % 4), 1),
            "wind_speed_kt": round(4.0 + (i % 6), 1),
            "wind_direction_deg": (90 + i * 15) % 360,
            "components": {
                "swell_size": round(5.0 + (i % 3), 1),
                "swell_direction": round(4.0 + (i % 4), 1),
                "wind": round(6.0 - (i % 3), 1),
                "period": round(7.0 + (i % 2), 1),
            },
        })
    return rows


def _slim_hour(row: dict) -> dict:
    return {k: row.get(k) for k in (
        "time", "score", "wave_height_m", "wave_period_s",
        "wind_speed_kt", "wind_direction_deg",
    )}


def _daily_best(scored: list[dict]) -> list[dict]:
    best_by_date: dict[str, dict] = {}
    for row in scored or []:
        date = str(row.get("time", ""))[:10]
        if not date:
            continue
        if date not in best_by_date or float(row.get("score", 0) or 0) > float(best_by_date[date].get("score", 0) or 0):
            best_by_date[date] = row
    return [
        {"date": d, **_slim_hour(best_by_date[d])}
        for d in sorted(best_by_date)
    ]


def _climate_slug(break_: dict) -> str:
    """Slug matching Worker B's ``data/climate/<name-state-region>.json`` files."""
    parts = [str(break_.get("name", "")), str(break_.get("state", "")), str(break_.get("region", ""))]
    slug = "-".join(parts).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "unknown"


# ---------------------------------------------------------------------------
# The 9 tools.
# ---------------------------------------------------------------------------

@tool
def get_spot_knowledge(spot_name: str, region: Optional[str] = None) -> dict:
    """Knowledge-base profile for one surf spot (ideals, hazards, skill).

    Args:
        spot_name: Name of the surf spot, e.g. 'Bells Beach'.
        region: State name, code or sub-region, e.g. 'Victoria' or 'VIC'.
    """
    b = _resolve_local(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return {k: b.get(k) for k in _KNOWLEDGE_KEYS if k in b}


@tool
def get_climate_profile(spot_name: str, region: Optional[str] = None) -> dict:
    """5-year wave climatology + dataset audit findings for one spot.

    Args:
        spot_name: Name of the surf spot, e.g. 'Bells Beach'.
        region: State name, code or sub-region, e.g. 'Victoria' or 'VIC'.
    """
    b = _resolve_local(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    slug = _climate_slug(b)
    if _HAS_CLIMATE and _core_load_climate is not None:
        try:
            climate = _core_load_climate(slug)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Climate load failed for '{spot_name}': {exc}"}
    else:
        # STUB(merge): plausible climate shape until wavereader.climate lands.
        climate = {
            "slug": slug,
            "years": 5,
            "direction_rose_pct": {"S": 28.0, "SE": 22.0, "SW": 18.0, "E": 12.0, "other": 20.0},
            "monthly_median_height_m": {str(m): round(1.2 + (m % 4) * 0.3, 1) for m in range(1, 13)},
            "monthly_median_period_s": {str(m): round(8.0 + (m % 3), 1) for m in range(1, 13)},
            "best_months": ["5", "6", "7"],
            "stub": True,
        }
    if _HAS_AUDIT and _core_audit_break is not None:
        try:
            findings = _core_audit_break(b, climate)
        except Exception as exc:  # noqa: BLE001
            findings = [{"field": "audit", "finding": f"audit failed: {exc}"}]
    else:
        # STUB(merge): plausible audit shape until wavereader.climate lands.
        findings = [{
            "field": "idealSwell.direction",
            "finding": "stub: no observed rose to compare against yet",
            "note": "rewire to audit_break at merge",
        }]
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "climate": climate,
        "findings": findings,
    }


@tool
def score_week(spot_name: str, region: Optional[str] = None, skill: Optional[str] = None) -> dict:
    """Hour-by-hour surf scores for the next 7 days at ONE spot.

    Args:
        spot_name: Name of the surf spot, e.g. 'Bells Beach'.
        region: State name, code or sub-region, e.g. 'Victoria'.
        skill: Surfer skill tier: beginner, intermediate, advanced, expert.
    """
    b = _resolve_local(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    skill_level = (skill or "intermediate").strip().lower() or "intermediate"
    # Real Worker A path when backends import; stable fake rows offline.
    scored, used_stub = _scored_or_fake(b, skill_level)
    if not scored and not used_stub:
        return {"error": f"No scored hours for '{spot_name}' ({region})"}
    daily = _daily_best(scored)
    best = max(scored, key=lambda r: float(r.get("score", 0) or 0)) if scored else None
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "skill": skill_level,
        "scored": scored,
        "daily": daily,
        "best": _slim_hour(best) if best else None,
        "stub": used_stub,
    }


@tool
def rank_region_week(region: str, skill: Optional[str] = None, limit: Optional[int] = None) -> dict:
    """Rank every break in a region by its best score this week.

    Args:
        region: State name, code or sub-region, e.g. 'Queensland' or 'QLD'.
        skill: Surfer skill tier filter.
        limit: Max spots to return (1-25).
    """
    if not (region or "").strip():
        return {"error": "Pass a state name, code, or sub-region"}
    try:
        lim = max(1, min(25, int(limit))) if limit is not None else 10
    except (TypeError, ValueError):
        lim = 10
    skill_level = (skill or "intermediate").strip().lower() or "intermediate"
    breaks = _load_breaks()
    candidates = [b for b in breaks if _region_matches(b, region)]
    if skill:
        candidates = [b for b in candidates if str(b.get("skillLevel", "")).lower() == skill_level]
    pool = candidates[:lim]
    if _HAS_RANK and _core_rank_spots is not None and _HAS_FORECAST and _core_get_forecast is not None:
        try:
            # Real Worker A path: forecasts keyed by (name, region) per
            # rank_spots(forecasts, spots_list, skill_level); skips fail.
            forecasts: dict[tuple[str, str], dict] = {}
            fetch_ok: list[dict] = []
            for b in pool:
                lat, lng = _coords(b)
                if lat is None or lng is None:
                    continue
                try:
                    forecasts[(str(b.get("name")), str(b.get("region")))] = _core_get_forecast(lat, lng, 7)
                    fetch_ok.append(b)
                except Exception:
                    continue
            if not fetch_ok:
                raise RuntimeError("no forecasts fetched (offline?)")
            ranked = _core_rank_spots(forecasts, fetch_ok, skill_level)
            used_stub = False
        except Exception as exc:  # noqa: BLE001 — offline? fall back to stable stub
            ranked = None
            rank_error = str(exc)
            used_stub = True
    else:
        ranked = None
        rank_error = ""
        used_stub = True
    if ranked is None:
        if used_stub and (_HAS_RANK and _HAS_FORECAST):
            # Backends exist but fetch failed (e.g. offline): surface it.
            if not pool:
                return {"region": region, "skill": skill_level, "spots": [], "count": 0,
                        "candidates": len(candidates), "stub": False,
                        "note": "No breaks matched — call list_regions() for spellings."}
            return {"error": f"Ranking failed for '{region}': {rank_error}"}
        # STUB(merge): stable pseudo-ranking until scoring lands.
        ranked = sorted(
            [{
                "name": b.get("name"),
                "region": b.get("region"),
                "best_score": _fake_score_for(str(b.get("name")), 0),
                "best_time": (_FAKE_WEEK_ANCHOR + timedelta(hours=6)).isoformat(),
                "skill_level": skill_level,
            } for b in pool],
            key=lambda r: float(r["best_score"]),
            reverse=True,
        )
        used_stub = True
    return {
        "region": region,
        "skill": skill_level,
        "spots": ranked,
        "count": len(ranked),
        "candidates": len(candidates),
        "stub": used_stub,
    }


@tool
def explain_score(
    spot_name: str,
    region: Optional[str] = None,
    skill: Optional[str] = None,
    time: Optional[str] = None,
) -> dict:
    """Explain WHY one scored hour got its score (component split).

    Args:
        spot_name: Name of the surf spot, e.g. 'Bells Beach'.
        region: State name, code or sub-region.
        skill: Surfer skill tier.
        time: Hour substring to explain, e.g. '2026-09-07T06'; default best hour.
    """
    b = _resolve_local(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    skill_level = (skill or "intermediate").strip().lower() or "intermediate"
    scored, used_stub = _scored_or_fake(b, skill_level)  # real Worker A hours when online
    target = None
    if time:
        for row in scored:
            if str(time).strip() in str(row.get("time", "")):
                target = row
                break
    target = target or (max(scored, key=lambda r: float(r.get("score", 0) or 0)) if scored else None)
    if target is None:
        return {"error": f"No scored hours for '{spot_name}'"}
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "skill": skill_level,
        "time": target.get("time"),
        "score": target.get("score"),
        "components": target.get("components"),
        "wave_height_m": target.get("wave_height_m"),
        "wave_period_s": target.get("wave_period_s"),
        "wind_speed_kt": target.get("wind_speed_kt"),
        "wind_direction_deg": target.get("wind_direction_deg"),
        "stub": used_stub,  # STUB(merge): True only when backends unavailable/offline
    }


@tool
def find_best_windows(
    spot_name: str,
    region: Optional[str] = None,
    skill: Optional[str] = None,
    daypart: Optional[str] = None,
    weekend_only: Optional[bool] = None,
    min_score: Optional[float] = None,
    limit: Optional[int] = None,
) -> dict:
    """Best scored windows at ONE spot with daypart/weekend filters.

    Args:
        spot_name: Name of the surf spot, e.g. 'Bells Beach'.
        region: State name, code or sub-region.
        skill: Surfer skill tier.
        daypart: morning (05-11), midday (11-15), afternoon (15-20), or all.
        weekend_only: Only Saturday/Sunday windows.
        min_score: Minimum score floor.
        limit: Max windows to return (1-10).
    """
    b = _resolve_local(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    skill_level = (skill or "intermediate").strip().lower() or "intermediate"
    part = (daypart or "all").strip().lower()
    ranges = {"morning": (5, 11), "midday": (11, 15), "afternoon": (15, 20), "all": (0, 24)}
    lo, hi = ranges.get(part, (0, 24))
    try:
        floor = max(0.0, float(min_score)) if min_score is not None else 0.0
    except (TypeError, ValueError):
        floor = 0.0
    try:
        lim = max(1, min(10, int(limit))) if limit is not None else 5
    except (TypeError, ValueError):
        lim = 5
    scored, used_stub = _scored_or_fake(b, skill_level)  # real Worker A hours when online
    kept = []
    for row in scored:
        try:
            dt = datetime.fromisoformat(str(row.get("time", "")))
        except ValueError:
            continue
        if not (lo <= dt.hour < hi):
            continue
        if weekend_only and dt.weekday() >= 5:
            pass
        elif weekend_only:
            continue
        if float(row.get("score", 0) or 0) < floor:
            continue
        kept.append(row)
    kept.sort(key=lambda r: float(r.get("score", 0) or 0), reverse=True)
    slim = [_slim_hour(r) for r in kept[:lim]]
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "skill": skill_level,
        "filters": {"daypart": part, "weekend_only": bool(weekend_only), "min_score": floor},
        "windows": slim,
        "best": slim[0] if slim else None,
        "stub": used_stub,  # STUB(merge): True only when backends unavailable/offline
    }


@tool
def find_spots(query: str = "", skill: Optional[str] = None, limit: Optional[int] = None) -> list:
    """Substring-search breaks by name, state or region.

    Args:
        query: Spot name, state name/code or sub-region, e.g. 'Byron' or 'QLD'.
        skill: Skill tier filter.
        limit: Max results (1-25).
    """
    q = (query or "").strip().lower()
    expanded = _expand_state_code(query) if q else None
    expanded_lower = expanded.lower() if expanded else None
    try:
        lim = max(1, min(25, int(limit))) if limit is not None else 10
    except (TypeError, ValueError):
        lim = 10
    skill_level = (skill or "").strip().lower() or None
    out = []
    for b in _load_breaks():
        if q:
            hay = (str(b.get("name", "")).lower(), str(b.get("state", "")).lower(), str(b.get("region", "")).lower())
            if not any(q in h for h in hay):
                if expanded_lower is None or not any(expanded_lower in h for h in hay[1:]):
                    continue
        if skill_level and str(b.get("skillLevel", "")).lower() != skill_level:
            continue
        out.append({k: b.get(k) for k in _SPOT_SUMMARY_KEYS})
        if len(out) >= lim:
            break
    return out


@tool
def find_similar_spots(
    spot_name: str, region: Optional[str] = None, limit: Optional[int] = None
) -> list:
    """Breaks most similar to a reference break (skill/type/peak/swell).

    Args:
        spot_name: Reference spot name, e.g. 'Snapper Rocks'.
        region: State name, code or sub-region.
        limit: Max results (1-10).
    """
    ref = _resolve_local(spot_name, region)
    if ref is None:
        return [{"error": f"Spot '{spot_name}' ({region}) not found"}]
    try:
        lim = max(1, min(10, int(limit))) if limit is not None else 5
    except (TypeError, ValueError):
        lim = 5

    def _sim(cand: dict) -> float:
        s = 0.0
        if str(ref.get("skillLevel", "")).lower() == str(cand.get("skillLevel", "")).lower():
            s += 3.0
        if ref.get("breakType") == cand.get("breakType"):
            s += 2.0
        if ref.get("peakType") == cand.get("peakType"):
            s += 2.0
        ref_dirs = set((ref.get("idealSwell") or {}).get("direction") or [])
        cand_dirs = set((cand.get("idealSwell") or {}).get("direction") or [])
        if ref_dirs & cand_dirs:
            s += 1.5
        if ref.get("state") == cand.get("state"):
            s += 1.0
        return round(s, 2)

    scored = []
    for b in _load_breaks():
        if str(b.get("name", "")).lower() == str(ref.get("name", "")).lower():
            continue
        scored.append((_sim(b), b))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [{**{k: b.get(k) for k in _SPOT_SUMMARY_KEYS}, "similarity": s} for s, b in scored[:lim]]


@tool
def list_regions() -> dict:
    """Canonical states + regions vocabulary. Call before guessing spellings."""
    breaks = _load_breaks()
    states = sorted({str(b.get("state", "")) for b in breaks if b.get("state")})
    regions_by_state: dict[str, set[str]] = {}
    for b in breaks:
        if b.get("state") and b.get("region"):
            regions_by_state.setdefault(str(b["state"]), set()).add(str(b["region"]))
    return {
        "states": states,
        "regions_by_state": {s: sorted(v) for s, v in sorted(regions_by_state.items())},
    }


#: The 9 tools in canonical order (agent + MCP share this list).
TOOLS = [
    get_spot_knowledge,
    get_climate_profile,
    score_week,
    rank_region_week,
    explain_score,
    find_best_windows,
    find_spots,
    find_similar_spots,
    list_regions,
]

TOOL_NAMES = [t.name for t in TOOLS]
