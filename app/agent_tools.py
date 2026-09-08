"""Agent tools: forecast/score/knowledge lookups over the enriched break list.

Ported from ``wavereader/tools.py`` onto ``data/australia-surf-breaks-enriched.json``.

Deterministic-only contract: no LLM, no smolagents, no Gradio. The only
network access is via ``app.forecasts.get_forecast`` (disk-cached Open-Meteo
client); scoring stays in ``app.scoring`` and spot shaping in ``app.adapters``.
The LLM never owns numbers — it only routes through these helpers.

Region handling: callers may pass a full state name (``"Victoria"``), a
sub-region (``"Central Coast"``), or a legacy state code (``NSW``, ``QLD``,
``VIC``, ``WA``, ``SA``, ``TAS``, ``NT``). Codes are expanded to full state
names before matching.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import adapters, forecasts, scoring

__all__ = [
    "get_forecast",
    "score_week",
    "find_spots",
    "get_spot_knowledge",
    "rank_spots_this_week",
    "explain_score_breakdown",
    "find_best_windows",
    "find_similar_spots",
    "list_states_regions",
    "get_spot_sun_sst",
]

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "australia-surf-breaks-enriched.json"

_STATE_CODE_TO_NAME = {
    "NSW": "New South Wales",
    "QLD": "Queensland",
    "VIC": "Victoria",
    "WA": "Western Australia",
    "SA": "South Australia",
    "TAS": "Tasmania",
    "NT": "Northern Territory",
}

_MAX_RANK_FANOUT = 15
_RANK_WORKERS = 8

_SPOT_SUMMARY_KEYS = ("name", "state", "region", "skillLevel", "breakType", "peakType")
_KNOWLEDGE_KEYS = (
    "name",
    "state",
    "region",
    "skillLevel",
    "breakType",
    "peakType",
    "idealSwell",
    "idealWind",
    "idealTide",
    "bestSeason",
    "hazards",
    "crowdFactor",
    "description",
    "location",
)


def _trim_spot(break_: dict) -> dict:
    """Token-lean summary for search/rank results."""
    return {k: break_.get(k) for k in _SPOT_SUMMARY_KEYS}


def _trim_knowledge(break_: dict) -> dict:
    """Token-lean knowledge profile (drops id/coords-adjacent extras)."""
    return {k: break_.get(k) for k in _KNOWLEDGE_KEYS if k in break_}


def _best_window(scored: list[dict]) -> dict | None:
    """Single highest-scoring hour, or None when empty (mirrors surf_forecast.best_window)."""
    if not scored:
        return None
    return max(scored, key=lambda r: r.get("score", 0))


def _daily_best(scored: list[dict]) -> list[dict]:
    """Best hour per calendar date (mirrors surf_forecast.daily_best).

    Kept inline so agent_tools never imports app.surf_forecast (which
    pulls plotly) — no circular-import / heavy-dep risk.
    """
    best_by_date: dict[str, dict] = {}
    for row in scored or []:
        date = str(row.get("time", ""))[:10]
        if not date:
            continue
        if date not in best_by_date or row.get("score", 0) > best_by_date[date].get(
            "score", 0
        ):
            best_by_date[date] = row
    out = []
    for date in sorted(best_by_date):
        row = best_by_date[date]
        out.append(
            {
                "date": date,
                "time": row.get("time"),
                "score": row.get("score"),
                "wave_height_m": row.get("wave_height_m"),
                "wave_period_s": row.get("wave_period_s"),
                "wind_speed_kt": row.get("wind_speed_kt"),
                "wind_direction_deg": row.get("wind_direction_deg"),
            }
        )
    return out


def _load_breaks(path: Path = _DATA_PATH) -> list[dict]:
    """Load enriched records; accept list or legacy ``{id: record}`` dict; drop errors."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        # Legacy format: {"name | state | region": {...}} mapping.
        records = list(data.values())
    else:
        records = list(data)
    return [r for r in records if isinstance(r, dict) and "error" not in r]


_BREAKS: list[dict] = _load_breaks()


def _normalize_skill(skill: str | None) -> str:
    """Normalize a skill query to a scoring tier (pro-only -> expert)."""
    return adapters.normalize_skill(skill)


def _expand_state_code(value: str | None) -> str | None:
    """Expand a legacy state code to its full name; None if not a code."""
    if not value:
        return None
    return _STATE_CODE_TO_NAME.get(value.strip().upper())


def _region_matches(break_: dict, region: str) -> bool:
    """True if ``region`` equals the break's state or sub-region (codes expanded)."""
    want = region.strip().lower()
    expanded = _expand_state_code(region)
    candidates = {str(break_.get("state", "")).lower(), str(break_.get("region", "")).lower()}
    if want in candidates:
        return True
    if expanded is not None and expanded.lower() in candidates:
        return True
    return False


def _resolve_break(name: str, region: str | None = None) -> dict | None:
    """Resolve a break by name (case-insensitive), preferring a region match.

    ``region`` accepts a full state name, a sub-region, or a legacy state
    code. When several records share a name, records matching ``region`` win;
    otherwise the first name match is returned. None when nothing matches.
    """
    if not name:
        return None
    want = name.strip().lower()
    exact = [b for b in _BREAKS if str(b.get("name", "")).lower() == want]
    candidates = exact or [b for b in _BREAKS if want in str(b.get("name", "")).lower()]
    if not candidates:
        return None
    if region:
        for b in candidates:
            if _region_matches(b, region):
                return b
    return candidates[0]


def get_spot_knowledge(spot_name: str, region: str | None = None) -> dict:
    """Return the trimmed knowledge profile for a break, or ``{"error": ...}``.

    ``region`` is optional; positional ``(spot_name, region)`` calls keep working.
    Network-free.
    """
    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return _trim_knowledge(b)


def get_forecast(spot_name: str, region: str | None = None) -> dict:
    """Fetch the 7-day forecast frame for a break; ``{"error": ...}`` on miss.

    ``region`` is optional; positional ``(spot_name, region)`` calls keep working.
    """
    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    lat, lng = adapters.get_coords(b)
    if lat is None or lng is None:
        return {"error": f"Spot '{spot_name}' ({region}) has no coordinates"}
    try:
        return forecasts.get_forecast(lat, lng)
    except Exception as e:  # noqa: BLE001 — surface fetch failure to the agent
        return {"error": f"Forecast fetch failed for '{spot_name}' ({region}): {e}"}


def score_week(
    spot_name: str, region: str | None = None, skill: str | None = None
) -> dict:
    """Score every forecast hour for a break; ``{"error": ...}`` on failure.

    ``region`` is optional; positional ``(spot_name, region, skill)`` calls
    keep working. Returns a token-lean wrapper
    ``{"spot", "skill", "scored", "daily", "best"}`` — ``scored`` holds the
    full hourly rows, ``daily`` the per-date bests, ``best`` the top hour.
    """
    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    lat, lng = adapters.get_coords(b)
    if lat is None or lng is None:
        return {"error": f"Spot '{spot_name}' ({region}) has no coordinates"}
    try:
        forecast = forecasts.get_forecast(lat, lng)
    except Exception as e:  # noqa: BLE001 — surface fetch failure to the agent
        return {"error": f"Forecast fetch failed for '{spot_name}' ({region}): {e}"}
    skill_level = _normalize_skill(skill)
    spot = adapters.enriched_to_scoring_spot(b)
    scored = scoring.score_week(forecast, spot, skill_level=skill_level)
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "skill": skill_level,
        "scored": scored,
        "daily": _daily_best(scored),
        "best": _best_window(scored),
    }


def _search_breaks(query: str = "", skill: str | None = None, limit: int = 10) -> list[dict]:
    """Full-record substring search (internal); ``find_spots`` trims on top."""
    q = (query or "").strip().lower()
    expanded = _expand_state_code(query) if q else None
    expanded_lower = expanded.lower() if expanded else None

    results: list[dict] = []
    for b in _BREAKS:
        if q:
            hay = (
                str(b.get("name", "")).lower(),
                str(b.get("state", "")).lower(),
                str(b.get("region", "")).lower(),
            )
            if not any(q in h for h in hay):
                if expanded_lower is None or not any(
                    expanded_lower in h for h in hay[1:]
                ):
                    continue
        if skill:
            if adapters.normalize_skill(b.get("skillLevel")) != _normalize_skill(skill):
                continue
        results.append(b)
        if len(results) >= limit:
            break
    return results


def find_spots(
    query: str = "",
    skill: str | None = None,
    limit: int = 10,
    region: str | None = None,
) -> list[dict]:
    """Substring-search breaks by name/state/region (state codes expanded).

    ``region`` is an alias for ``query`` (``query or region`` wins) so both
    ``find_spots(query="VIC")`` and ``find_spots(region="VIC")`` work.
    Skill filters on the normalized tier. Returns trimmed
    ``{name,state,region,skillLevel,breakType,peakType}`` dicts, capped at
    ``limit``. Network-free.
    """
    effective = (query or region or "") if query or region else ""
    try:
        lim = max(1, int(limit))
    except (TypeError, ValueError):
        lim = 10
    return [_trim_spot(b) for b in _search_breaks(effective, skill=skill, limit=lim)]


def _rank_one(break_: dict, skill_level: str) -> dict | None:
    """Fetch + score one break; None on any failure (coords/fetch/empty)."""
    lat, lng = adapters.get_coords(break_)
    if lat is None or lng is None:
        return None
    try:
        frame = forecasts.get_forecast(lat, lng)
    except Exception:  # noqa: BLE001 — skip unfetchable breaks, rank the rest
        return None
    try:
        spot = adapters.enriched_to_scoring_spot(break_)
        hours = scoring.score_week(frame, spot, skill_level=skill_level)
    except Exception:  # noqa: BLE001 — skip unscoreable breaks, rank the rest
        return None
    best = _best_window(hours)
    if best is None:
        return None
    return {
        "name": break_.get("name"),
        "region": break_.get("region"),
        "best_score": best.get("score", 0.0),
        "best_time": best.get("time"),
        "skill_level": skill_level,
    }


def rank_spots_this_week(
    region: str,
    skill: str | None = None,
    break_type: str | None = None,
    peak_type: str | None = None,
    max_crowd: str | None = None,
    avoid_hazards: list[str] | str | None = None,
    limit: int = 15,
) -> list[dict]:
    """Rank breaks in ``region`` by best hourly score this week.

    Forecast fetch + scoring fan out over a ThreadPoolExecutor (max 8
    workers); failures are skipped. Optional deterministic filters
    (applied before scoring so the LLM never filters by hand):
    ``break_type`` / ``peak_type`` exact match, ``max_crowd`` caps
    quiet<moderate<busy<very crowded, ``avoid_hazards`` drops any break
    carrying a listed hazard. Returns sorted trimmed rows
    ``[{name,region,best_score,best_time,skill_level}]`` — no full
    ``best_hour`` blob — to save tokens.
    """
    crowd_order = {"quiet": 0, "moderate": 1, "busy": 2, "very crowded": 3}
    avoid: set[str] = set()
    if isinstance(avoid_hazards, str):
        avoid = {avoid_hazards.strip().lower()} if avoid_hazards.strip() else set()
    elif isinstance(avoid_hazards, list):
        avoid = {str(h).strip().lower() for h in avoid_hazards if str(h).strip()}
    try:
        lim = max(1, min(25, int(limit)))
    except (TypeError, ValueError):
        lim = 15
    candidates = _search_breaks(query=region or "", skill=skill, limit=1000)
    if break_type:
        want = str(break_type).strip().lower()
        candidates = [b for b in candidates if str(b.get("breakType", "")).lower() == want]
    if peak_type:
        want = str(peak_type).strip().lower()
        candidates = [b for b in candidates if str(b.get("peakType", "")).lower() == want]
    if max_crowd:
        cap = crowd_order.get(str(max_crowd).strip().lower())
        if cap is not None:
            candidates = [
                b for b in candidates
                if crowd_order.get(str(b.get("crowdFactor", "moderate")).lower(), 1) <= cap
            ]
    if avoid:
        candidates = [
            b for b in candidates
            if not (set(str(h).lower() for h in (b.get("hazards") or [])) & avoid)
        ]
    candidates = candidates[:lim]
    if not candidates:
        return []
    skill_level = _normalize_skill(skill)
    ranked: list[dict] = []
    with ThreadPoolExecutor(max_workers=_RANK_WORKERS) as pool:
        for row in pool.map(lambda b: _rank_one(b, skill_level), candidates):
            if row is not None:
                ranked.append(row)
    ranked.sort(key=lambda x: x["best_score"], reverse=True)
    return ranked


_CROWD_ORDER = {"quiet": 0, "moderate": 1, "busy": 2, "very crowded": 3}

_WETSUIT_TABLE = (
    (22.0, "boardshorts / rashie"),
    (19.0, "2mm spring suit"),
    (16.0, "3/2mm full suit"),
    (float("-inf"), "4/3mm full suit + boots in winter"),
)


def _wetsuit_hint(sst_c) -> str | None:
    try:
        sst = float(sst_c)
    except (TypeError, ValueError):
        return None
    for threshold, hint in _WETSUIT_TABLE:
        if sst >= threshold:
            return f"{hint} (SST ~{sst:.1f}C)"
    return None


def list_states_regions() -> dict:
    """Return the canonical state/region vocabulary (network-free).

    Use this when unsure of a region spelling instead of guessing —
    every ``region`` arg on other tools must come from here.
    """
    states = sorted({str(b.get("state", "")) for b in _BREAKS if b.get("state")})
    regions_by_state: dict[str, set[str]] = {}
    for b in _BREAKS:
        state, region = b.get("state"), b.get("region")
        if state and region:
            regions_by_state.setdefault(str(state), set()).add(str(region))
    return {
        "states": states,
        "regions_by_state": {s: sorted(v) for s, v in sorted(regions_by_state.items())},
    }


def get_spot_sun_sst(spot_name: str, region: str | None = None) -> dict:
    """Return daily sunrise/sunset + latest sea-surface temp for a break.

    All values come from the cached Open-Meteo frame (no new API).
    ``wetsuit_hint`` is a deterministic SST lookup table, not LLM advice.
    """
    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    lat, lng = adapters.get_coords(b)
    if lat is None or lng is None:
        return {"error": f"Spot '{spot_name}' ({region}) has no coordinates"}
    try:
        frame = forecasts.get_forecast(lat, lng)
    except Exception as e:  # noqa: BLE001 — surface fetch failure to the agent
        return {"error": f"Forecast fetch failed for '{spot_name}' ({region}): {e}"}
    daily = frame.get("daily") or {}
    sst = None
    for row in (frame.get("hourly") or [])[:6]:
        if isinstance(row, dict) and row.get("sea_surface_temperature") is not None:
            sst = row.get("sea_surface_temperature")
            break
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "sunrise": daily.get("sunrise"),
        "sunset": daily.get("sunset"),
        "sea_surface_temp_c": sst,
        "wetsuit_hint": _wetsuit_hint(sst),
    }


def explain_score_breakdown(
    spot_name: str, region: str | None = None, skill: str | None = None, time: str | None = None
) -> dict:
    """Explain WHY one scored hour got its score (deterministic components).

    Resolves ``time`` as a substring match (e.g. ``"2026-09-05T07"``);
    defaults to the best hour. Returns the component split
    (swell_size / swell_direction / wind / period) plus raw inputs so
    the agent can narrate without inventing numbers.
    """
    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    lat, lng = adapters.get_coords(b)
    if lat is None or lng is None:
        return {"error": f"Spot '{spot_name}' ({region}) has no coordinates"}
    try:
        frame = forecasts.get_forecast(lat, lng)
    except Exception as e:  # noqa: BLE001 — surface fetch failure to the agent
        return {"error": f"Forecast fetch failed for '{spot_name}' ({region}): {e}"}
    skill_level = _normalize_skill(skill)
    spot = adapters.enriched_to_scoring_spot(b)
    scored = scoring.score_week(frame, spot, skill_level=skill_level)
    if not scored:
        return {"error": f"No scored hours for '{spot_name}' ({region})"}
    target = None
    if time:
        want = str(time).strip()
        for row in scored:
            if want in str(row.get("time", "")):
                target = row
                break
    target = target or _best_window(scored)
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
        "gust_kt": target.get("gust_kt"),
    }


def find_best_windows(
    spot_name: str,
    region: str | None = None,
    skill: str | None = None,
    daypart: str | None = None,
    weekend_only: bool = False,
    min_score: float = 0.0,
    max_wind_kt: float | None = None,
    limit: int = 5,
) -> dict:
    """Filter one spot's scored week to the best matching windows.

    ``daypart``: ``"morning"`` (05-11), ``"midday"`` (11-15),
    ``"afternoon"`` (15-20), or ``"all"``. ``weekend_only`` keeps
    Sat/Sun. Deterministic post-filter so the LLM never does time math.
    """
    from datetime import datetime as _dt

    b = _resolve_break(spot_name, region)
    if b is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    lat, lng = adapters.get_coords(b)
    if lat is None or lng is None:
        return {"error": f"Spot '{spot_name}' ({region}) has no coordinates"}
    try:
        frame = forecasts.get_forecast(lat, lng)
    except Exception as e:  # noqa: BLE001 — surface fetch failure to the agent
        return {"error": f"Forecast fetch failed for '{spot_name}' ({region}): {e}"}
    skill_level = _normalize_skill(skill)
    spot = adapters.enriched_to_scoring_spot(b)
    scored = scoring.score_week(frame, spot, skill_level=skill_level)
    part = (daypart or "all").strip().lower()
    ranges = {"morning": (5, 11), "midday": (11, 15), "afternoon": (15, 20), "all": (0, 24)}
    lo, hi = ranges.get(part, (0, 24))
    try:
        floor = max(0.0, float(min_score))
    except (TypeError, ValueError):
        floor = 0.0
    try:
        lim = max(1, min(10, int(limit)))
    except (TypeError, ValueError):
        lim = 5
    kept = []
    for row in scored:
        try:
            hour = _dt.fromisoformat(str(row.get("time", ""))).hour
        except ValueError:
            continue
        if not (lo <= hour < hi):
            continue
        if weekend_only:
            try:
                if _dt.fromisoformat(str(row.get("time", ""))).weekday() < 5:
                    continue
            except ValueError:
                continue
        if float(row.get("score", 0) or 0) < floor:
            continue
        if max_wind_kt is not None:
            try:
                if float(row.get("wind_speed_kt", 0) or 0) > float(max_wind_kt):
                    continue
            except (TypeError, ValueError):
                pass
        kept.append(row)
    kept.sort(key=lambda r: float(r.get("score", 0) or 0), reverse=True)
    slim = [
        {
            "time": r.get("time"),
            "score": r.get("score"),
            "wave_height_m": r.get("wave_height_m"),
            "wave_period_s": r.get("wave_period_s"),
            "wind_speed_kt": r.get("wind_speed_kt"),
            "wind_direction_deg": r.get("wind_direction_deg"),
        }
        for r in kept[:lim]
    ]
    return {
        "spot": {"name": b.get("name"), "state": b.get("state"), "region": b.get("region")},
        "skill": skill_level,
        "filters": {
            "daypart": part,
            "weekend_only": bool(weekend_only),
            "min_score": floor,
            "max_wind_kt": max_wind_kt,
        },
        "windows": slim,
        "best": slim[0] if slim else None,
    }


def _similarity_score(ref: dict, cand: dict) -> float:
    """Small deterministic similarity score (higher = more similar)."""
    score = 0.0
    if (ref.get("skillLevel") or "").lower() == (cand.get("skillLevel") or "").lower():
        score += 3.0
    if ref.get("breakType") == cand.get("breakType"):
        score += 2.0
    if ref.get("peakType") == cand.get("peakType"):
        score += 2.0
    ref_dirs = set((ref.get("idealSwell") or {}).get("direction") or [])
    cand_dirs = set((cand.get("idealSwell") or {}).get("direction") or [])
    if ref_dirs & cand_dirs:
        score += 1.5
    try:
        ref_size = (ref.get("idealSwell") or {}).get("sizeRangeFt") or {}
        cand_size = (cand.get("idealSwell") or {}).get("sizeRangeFt") or {}
        score -= abs(float(ref_size.get("min", 0)) - float(cand_size.get("min", 0))) * 0.2
        score -= abs(float(ref_size.get("max", 0)) - float(cand_size.get("max", 0))) * 0.1
    except (TypeError, ValueError):
        pass
    if ref.get("state") == cand.get("state"):
        score += 1.0
    return round(score, 2)


def find_similar_spots(
    spot_name: str, region: str | None = None, skill: str | None = None, limit: int = 5
) -> list[dict] | dict:
    """Return breaks most similar to a reference break (network-free).

    Similarity: same skill tier (+3), breakType (+2), peakType (+2),
    shared swell direction (+1.5), size-range closeness, same state (+1).
    """
    ref = _resolve_break(spot_name, region)
    if ref is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    try:
        lim = max(1, min(10, int(limit)))
    except (TypeError, ValueError):
        lim = 5
    scored = []
    for b in _BREAKS:
        if b is ref:
            continue
        if str(b.get("name", "")).lower() == str(ref.get("name", "")).lower():
            continue
        if skill and adapters.normalize_skill(b.get("skillLevel")) != _normalize_skill(skill):
            continue
        scored.append((_similarity_score(ref, b), b))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [{**_trim_spot(b), "similarity": s} for s, b in scored[:lim]]
