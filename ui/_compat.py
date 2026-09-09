"""Backend access layer: real ``wavereader.*`` modules win, fallbacks below.

Resolution order per capability (first success wins):

1. ``wavereader.*`` — the real v2 core (Worker A: breaks/openmeteo/scoring/
   seafloor; Worker B: climate). Present on this branch: use it.
2. ``app.*`` — v1 modules still in the tree (same payload shapes, live data).
3. ``ui._stubs`` — deterministic fakes (offline-safe, used by smoke tests).

Worker C (``wavereader.tools`` / ``agent`` / ``narrate``) is absent on this
branch right now, so the tool functions below are implemented directly on
the Worker A/B core with the exact signatures the plan agreed
(``score_week`` / ``rank_region_week`` / ``explain_score``); when Worker C
lands, only this module changes — panels, charts and root ``app.py`` already
speak typed tool payloads.

Standing rule: never read ``.env`` or log secrets here. The BYO HF token
is passed straight through to narrate/agent factories and never stored.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ui import _stubs as _stub

ALL = "All"


def _core():
    """Worker A/B core modules, or None when unavailable (Worker branches)."""
    try:
        from wavereader import breaks as _b
        from wavereader import climate as _c
        from wavereader import openmeteo as _o
        from wavereader import scoring as _s
        from wavereader import seafloor as _sf
        return _b, _o, _s, _c, _sf
    except ImportError:
        return None


# ---------------------------------------------------------------- breaks ---

def list_breaks() -> list[dict]:
    """Full break catalogue as validated record dicts (real core first)."""
    core = _core()
    if core is not None:
        try:
            return core[0].load_breaks()
        except Exception:
            pass
    try:  # v1 catalogue (238 enriched breaks)
        from app.breaks_data import _records as _rec  # type: ignore
        from app.breaks_data import DF as _DF  # type: ignore

        return list(_rec(_DF))
    except ImportError:
        pass
    return [dict(b) for b in _stub.STUB_BREAKS]


def index_breaks(records: list[dict]) -> dict:
    """Derived filter vocab: states, regions-by-state, all regions, skills."""
    states = sorted({str(r.get("state", "?")) for r in records})
    regions_by_state: dict[str, list[str]] = {}
    for s in states:
        regions_by_state[s] = sorted({str(r.get("region", "?")) for r in records if str(r.get("state")) == s})
    all_regions = sorted({str(r.get("region", "?")) for r in records})
    order = _stub.SKILL_ORDER
    have = {str(r.get("skillLevel", "")).lower() for r in records}
    skills = [s for s in order if s in have] or sorted(have)
    return {"states": states, "regions_by_state": regions_by_state,
            "all_regions": all_regions, "skills": skills}


def filter_records(records: list[dict], state: str | None = None,
                   region: str | None = None, skill: str | None = None) -> list[dict]:
    """One-way filter (\"All\"/None = no filter, case-insensitive)."""
    core = _core()
    if core is not None:
        try:
            return core[0].filter_breaks(records, state=state, region=region, skill=skill)
        except Exception:
            pass
    out = records
    if state and state != ALL:
        out = [r for r in out if str(r.get("state", "")).lower() == state.lower()]
    if region and region != ALL:
        out = [r for r in out if str(r.get("region", "")).lower() == region.lower()]
    if skill and skill != ALL:
        out = [r for r in out if str(r.get("skillLevel", "")).lower() == skill.lower()]
    return out


def find_break(records: list[dict], name: str | None) -> dict | None:
    """Find a record by name (fuzzy via the real core, exact fallback)."""
    if not name:
        return None
    core = _core()
    if core is not None:
        try:
            hit = core[0].resolve_break(name, breaks=records)
            if hit is not None:
                return hit
        except Exception:
            pass
    want = str(name).strip().lower()
    for r in records or []:
        if str(r.get("name", "")).strip().lower() == want:
            return r
    return None


# --------------------------------------------------------------- scoring ---

def _score_with_core(break_: dict, skill: str, days: int) -> tuple[list[dict], dict]:
    """Fetch + score via Worker A core. Raises on any failure (caller falls back)."""
    core = _core()
    if core is None:
        raise ImportError("wavereader core unavailable")
    _b, _o, _s, _c, _sf = core
    lat, lng = _b.get_coords(break_)
    if lat is None or lng is None:
        raise ValueError(f"Missing coordinates for break {break_.get('name', '?')!r}")
    spot = _s.enriched_to_scoring_spot(break_)
    forecast = _o.get_forecast(lat, lng, days)
    scored = _s.score_week(forecast, spot, skill)
    return scored, spot


def _normalize_payload(break_: dict, skill: str, scored: list[dict],
                       spot: dict) -> dict:
    """One payload shape for every backend: scored/daily/daily_best/best."""
    from ui.charts import score as _sc

    best = max(scored, key=lambda r: float(r.get("score") or 0)) if scored else None
    return {
        "break": break_,
        "skill": skill,
        "spot": spot,
        "scored": scored,
        "daily": _sc.daily_summary(scored),
        "daily_best": _sc.daily_best(scored),
        "best": best,
        "sun": {},
        "sst_c": None,
        "wetsuit_hint": None,
    }


def get_scored_week(break_: dict | None, skill: str = "intermediate",
                    days: int = 7) -> dict:
    """Full scored payload for one break (core → v1 → stub; never hits LLM)."""
    if not break_:
        raise ValueError("No break selected")
    skill = (skill or "intermediate").strip().lower()
    days = max(1, min(7, int(days or 7)))
    try:
        scored, spot = _score_with_core(break_, skill, days)
        return _normalize_payload(break_, skill, scored, spot)
    except (ImportError, ValueError):
        raise
    except Exception:
        pass
    try:  # v1 deterministic path (network: Open-Meteo marine + wind)
        from app import surf_forecast as _mod  # type: ignore

        result = _mod.get_scored_week(break_, skill=skill, days=days)
        scored = result.get("scored", []) or []
        payload = _normalize_payload(break_, result.get("skill", skill), scored,
                                     result.get("spot", {}))
        payload["sun"] = result.get("sun") or {}
        payload["sst_c"] = result.get("sst_c")
        payload["wetsuit_hint"] = result.get("wetsuit_hint")
        return payload
    except ImportError:
        pass
    hours = _stub.stub_scored_hours(break_, skill=skill, days=days)
    return _normalize_payload(
        break_, skill, hours,
        {"name": break_.get("name"), "region": break_.get("region")})


def api_score_week(spot_name: str, region: str = "",
                   skill: str = "intermediate") -> dict:
    """Typed ``score_week`` tool (single source for agent + MCP + UI fallback)."""
    try:  # Worker C tools module, when it lands back on the branch
        from wavereader import tools as _t  # type: ignore

        out = _t.score_week(spot_name=spot_name, region=region or None, skill=skill)  # type: ignore[attr-defined]
        if isinstance(out, dict):
            return dict(out)
    except ImportError:
        pass
    records = list_breaks()
    core = _core()
    break_ = None
    if core is not None:
        try:
            break_ = core[0].resolve_break(spot_name, region or None, records)
        except Exception:
            break_ = None
    if break_ is None:
        break_ = find_break(records, spot_name)
    if break_ is None:
        return {"error": f"unknown spot {spot_name!r}"}
    try:
        payload = get_scored_week(break_, skill=skill, days=7)
    except (ValueError, RuntimeError) as e:
        return {"error": str(e)}
    return {"spot": payload["spot"], "skill": payload["skill"],
            "scored": payload["scored"], "daily": payload["daily"],
            "daily_best": payload["daily_best"], "best": payload["best"]}


def api_rank_region_week(region: str, skill: str = "intermediate",
                         limit: int = 10) -> dict:
    """Typed ``rank_region_week`` tool: rank a region's breaks by best score."""
    try:  # Worker C tools module, when it lands back on the branch
        from wavereader import tools as _t  # type: ignore

        out = _t.rank_region_week(region=region, skill=skill)  # type: ignore[attr-defined]
        if isinstance(out, dict):
            out = dict(out)
            out.setdefault("rank", out.get("spots"))
            return out
    except ImportError:
        pass
    skill = (skill or "intermediate").strip().lower()
    records = list_breaks()
    want = (region or "").strip().lower()
    cands = [r for r in records
             if str(r.get("state", "")).lower() == want or str(r.get("region", "")).lower() == want]
    if not cands:
        return {"error": f"unknown region {region!r}"}
    core = _core()
    rows: list[dict] = []
    if core is not None:
        _b, _o, _s, _c, _sf = core
        try:
            lim = max(1, min(12, int(limit)))
        except (TypeError, ValueError):
            lim = 10
        spots, forecasts = [], {}
        for b in cands[:lim]:
            try:
                spot = _s.enriched_to_scoring_spot(b)
                lat, lng = _b.get_coords(b)
                if lat is None or lng is None:
                    continue
                forecasts[(spot["name"], spot["region"])] = _o.get_forecast(lat, lng, 2)
                spots.append(spot)
            except Exception:
                continue
        if spots:
            try:
                rows = _s.rank_spots(forecasts, spots, skill)
            except Exception:
                rows = []
    if not rows:  # offline fallback: stub-rank the candidates deterministically
        for b in cands[:10]:
            hours = _stub.stub_scored_hours(b, skill=skill, days=2)
            best = max(hours, key=lambda r: r.get("score", 0)) if hours else {}
            rows.append({"name": b.get("name"), "region": b.get("region"),
                         "best_score": best.get("score"), "best_time": best.get("time")})
        rows.sort(key=lambda r: r.get("best_score") or 0, reverse=True)
    return {"region": region, "skill": skill, "rank": rows}


def api_explain_score(spot_name: str, skill: str = "intermediate",
                      time: str = "") -> dict:
    """Typed ``explain_score`` tool: score + component split for one hour."""
    try:  # Worker C tools module, when it lands back on the branch
        from wavereader import tools as _t  # type: ignore

        out = _t.explain_score(spot_name=spot_name, skill=skill, time=time or None)  # type: ignore[attr-defined]
        if isinstance(out, dict):
            return dict(out)
    except ImportError:
        pass
    payload = api_score_week(spot_name, skill=skill)
    if "error" in payload:
        return payload
    hours = payload.get("scored") or []
    row = next((h for h in hours if time and time in str(h.get("time", ""))), None)
    row = row or (max(hours, key=lambda r: float(r.get("score") or 0)) if hours else None)
    if row is None:
        return {"error": f"no scored hours for {spot_name!r}"}
    return {"spot": payload["spot"], "skill": payload["skill"], "time": row.get("time"),
            "score": row.get("score"), "components": row.get("components"),
            "wave_height_m": row.get("wave_height_m"), "wave_period_s": row.get("wave_period_s"),
            "wind_speed_kt": row.get("wind_speed_kt"),
            "wind_direction_deg": row.get("wind_direction_deg")}


# ------------------------------------------------------- climate + audit ---

_MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _break_slug(break_: dict) -> str:
    from wavereader import climate as _c

    break_id = f"{break_.get('name', '')} | {break_.get('state', '')} | {break_.get('region', '')}"
    return _c.slugify(break_id)


def get_climate_profile(break_: dict | None) -> dict:
    """5-year swell climate profile: ``{rose, best_months, medians}``.

    Real Worker B profile when the break's climate file exists (63/238
    built so far), else the deterministic stub profile — same shape, so
    the rose chart never breaks.
    """
    if not break_:
        return {}
    core = _core()
    if core is not None:
        try:
            _b, _o, _s, _c, _sf = core
            prof = _c.load_climate(_break_slug(break_))
            rose = dict(prof.get("direction_rose_pct") or {})
            monthly = prof.get("monthly") or {}
            ranked = sorted(monthly.items(),
                            key=lambda kv: float((kv[1] or {}).get("days_in_ideal_window") or 0),
                            reverse=True)
            best_months = [_MONTH_ABBR[int(m) - 1] for m, _ in ranked[:3] if str(m).isdigit()]
            heights = [float(v.get("median_swell_height_m")) for _, v in ranked
                       if isinstance(v, dict) and v.get("median_swell_height_m") is not None]
            periods = [float(v.get("median_swell_period_s")) for _, v in ranked
                       if isinstance(v, dict) and v.get("median_swell_period_s") is not None]
            heights.sort()
            periods.sort()
            if rose and any(v > 0 for v in rose.values()):
                return {"rose": rose, "best_months": best_months,
                        "median_height_m": round(heights[len(heights) // 2], 2) if heights else None,
                        "median_period_s": round(periods[len(periods) // 2], 1) if periods else None,
                        "source": "era5-5yr"}
        except Exception:
            pass
    prof = _stub.climate_profile(break_)
    prof["source"] = "stub"
    return prof


_SEV_TO_LEVEL = {"low": "info", "medium": "warn", "high": "warn"}


def get_audit_findings(break_: dict | None) -> list[dict]:
    """Climate-audit findings as ``[{level, message}]`` chips."""
    if not break_:
        return []
    core = _core()
    if core is not None:
        try:
            _b, _o, _s, _c, _sf = core
            prof = _c.load_climate(_break_slug(break_))
            findings = _c.audit_break(break_, prof)
            out = []
            for f in findings or []:
                sev = str(f.get("severity", "low")).lower()
                out.append({"level": _SEV_TO_LEVEL.get(sev, "info"),
                            "message": f"{f.get('field')}: dataset {f.get('dataset_value')} vs "
                                       f"climate {f.get('climate_value')}"})
            if out:
                return out
            return [{"level": "ok", "message": "dataset ideals agree with the 5-yr observed climate."}]
        except Exception:
            pass
    return _stub.audit_break(break_)


# --------------------------------------------------------------- seafloor ---

def get_seafloor(break_: dict | None, radius_km: float = 1.2) -> dict:
    """Bathymetry grid + deterministic markdown + stats for one break."""
    if not break_:
        raise ValueError("No break selected")
    coords = ((break_ or {}).get("location") or {}).get("coordinates") or {}
    try:
        lat, lng = float(coords["lat"]), float(coords["lng"])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Missing coordinates for break {break_.get('name', '?')!r}")
    core = _core()
    if core is not None:
        try:
            return dict(core[4].get_seafloor(lat, lng, radius_km=radius_km))
        except Exception:
            pass
    try:  # v1 seafloor (network: OpenTopoData)
        from app import seafloor as _s2  # type: ignore

        return dict(_s2.get_seafloor(lat, lng, radius_km=radius_km))
    except ImportError:
        pass
    grid = _stub.seafloor_grid(break_, radius_km=radius_km)
    return {"grid": grid, "analysis": "_Stub seafloor — real GEBCO grid lands with Worker A._",
            "stats": {"dataset": "stub-gebco"}}


# ---------------------------------------------------------------- narrate ---

def _deterministic_report(payload: dict) -> str:
    """Numbers-in, prose-out fallback: daily lines + recommendation, no LLM."""
    break_ = payload.get("break") or {}
    name = break_.get("name", "?")
    skill = payload.get("skill", "intermediate")
    daily = payload.get("daily_best") or payload.get("daily") or []
    best = payload.get("best") or {}
    lines = [f"### {name} — {skill} outlook (deterministic draft)"]
    for d in daily:
        lines.append(
            f"- **{d.get('date', str(d.get('time', ''))[:10])}**: {d.get('score')}/10 @ {d.get('time')} — "
            f"{d.get('wave_height_m')}m @ {d.get('wave_period_s')}s, "
            f"wind {d.get('wind_speed_kt')}kt."
        )
    if best:
        lines.append(f"\n**Recommendation:** {best.get('score')}/10 @ {best.get('time')} "
                     f"looks like the pick of the week.")
    wetsuit = payload.get("wetsuit_hint")
    if wetsuit:
        lines.append(f"🤿 {wetsuit}.")
    return "\n".join(lines)


def narrate_stream(payload: dict | None, hf_token: str = "") -> Iterator[str]:
    """Stream a surf-report markdown for a scored payload (LLM → fallback).

    Tries Worker C ``wavereader/narrate.py``, then the v1 report streamer
    (token arg first, ``HF_TOKEN`` env as fallback), then the deterministic
    template so the button always produces markdown offline.
    """
    if not payload or not (payload.get("daily_best") or payload.get("daily")):
        yield "_No scored forecast yet — pick a break first._"
        return
    daily = payload.get("daily_best") or []
    try:  # Worker C narrator (Nemotron, numbers-in prose-out)
        from wavereader import narrate as _n  # type: ignore

        for chunk in _n.generate_report_stream(  # type: ignore[attr-defined]
                payload.get("break") or {}, payload.get("skill", "intermediate"),
                daily, payload.get("best"), payload.get("days", len(daily)),
                hf_token=(hf_token or "").strip() or None):
            yield chunk
        return
    except ImportError:
        pass
    except Exception:
        pass
    try:  # v1 report streamer (InferenceClient, token from env)
        from app import generate_surf_report as _rep  # type: ignore

        for chunk in _rep.generate_surf_report_stream(
                break_=payload.get("break") or {}, skill=payload.get("skill", "intermediate"),
                daily=daily, best=payload.get("best"),
                days=payload.get("days", len(daily))):
            yield chunk
        return
    except Exception:
        pass
    text = _deterministic_report(payload)  # offline fallback, chunked like a stream
    words = text.split(" ")
    for i in range(1, len(words) + 1, 24):
        yield " ".join(words[:i])


# ------------------------------------------------------------------- agent ---

def _stub_agent_stream(message: str, skill: str,
                       selected_break: dict | None) -> Iterator[tuple[str, Any]]:
    """Offline agent: one stub score_week call → charts + meter + answer."""
    name = (selected_break or {}).get("name") or "Bells Beach"
    region = (selected_break or {}).get("region") or ""
    args = {"spot_name": name, "region": region, "skill": skill}
    yield ("tool_call", {"name": "score_week", "arguments": args})
    payload = api_score_week(name, region, skill)
    hours = payload.get("scored") or []
    yield ("tool_result", {"name": "score_week", "arguments": args,
                           "observation": payload,
                           "summary": f"{len(hours)} scored hour(s) for {name}"})
    yield ("usage", {"prompt_tokens": 1180, "completion_tokens": 210})
    best = payload.get("best") or {}
    yield ("final", f"**{name}** looks surfable — best **{best.get('score')}/10 "
                    f"@ {best.get('time')}** ({best.get('wave_height_m')}m @ "
                    f"{best.get('wave_period_s')}s). _Stub answer — the real "
                    f"Nemotron agent lands with Worker C._")


def _real_agent_stream(question: str, hf_token: str) -> Iterator[tuple[str, Any]]:
    """Adapt Worker C dict events to the panel's (kind, payload) tuples."""
    from wavereader import agent as _a  # type: ignore

    for event in _a.run_stream(question, hf_token=(hf_token or "").strip() or None):  # type: ignore[attr-defined]
        kind = event.get("kind")
        if kind == "token":
            yield ("token", event.get("text", ""))
        elif kind == "tool_call":
            yield ("tool_call", {"name": event.get("name", "?"),
                                 "arguments": event.get("arguments", {})})
        elif kind == "tool_result":
            yield ("tool_result", {"name": event.get("name", "?"), "arguments": {},
                                   "observation": event.get("output"),
                                   "summary": event.get("summary", "")})
        elif kind == "final":
            yield ("final", event.get("text", ""))
        elif kind == "usage":
            yield ("usage", {"steps": event.get("steps"), "tool_calls": event.get("tool_calls"),
                             "model": event.get("model"), "provider": event.get("provider"),
                             "max_tokens": event.get("max_tokens")})


def _v1_agent_stream(message: str, skill: str, hf_token: str,
                     selected_break: dict | None) -> Iterator[tuple[str, Any]]:
    """Adapt the v1 CodeAgent stream (app/agent.py) to typed v2 events."""
    from app import agent as _am  # type: ignore

    agent = _am.SurfAgent(hf_token=(hf_token or "").strip() or None)
    for kind, data in agent.run_stream(message):
        if kind == "model":
            yield ("token", data)
        elif kind == "tool_start":
            d = data if isinstance(data, dict) else {"name": str(data)}
            yield ("tool_call", {"name": d.get("name", "?"),
                                 "arguments": d.get("arguments", {})})
        elif kind == "tool_end":
            d = data if isinstance(data, dict) else {"name": "?", "summary": str(data)}
            yield ("tool_result", {"name": d.get("name", "?"),
                                   "arguments": {},
                                   "observation": d.get("observation"),
                                   "summary": d.get("summary", "")})
        elif kind == "final":
            yield ("final", data)
        # ("tool", "code") kinds are display-only in v1 — skip here.


def agent_run_stream(message: str, skill: str = "intermediate",
                     hf_token: str = "", selected_break: dict | None = None,
                     ) -> Iterator[tuple[str, Any]]:
    """Yield typed agent events: token | tool_call | tool_result | final | usage.

    Worker C ``wavereader/agent.py`` first (native tool calling), then the
    v1 CodeAgent adapter, then the offline stub. ``hf_token`` is session-only
    and is never logged or persisted.
    """
    skill = (skill or "intermediate").strip().lower()
    sel = selected_break or {}
    context = ", ".join(p for p in (sel.get("name"), sel.get("region"), sel.get("state")) if p)
    question = message
    if context or skill:
        question = (f"[surfer skill level = {skill}"
                    + (f"; user is viewing {context}" if context else "") + "]\n" + message)
    try:  # Worker C: ToolCallingAgent with real ToolCall/ToolOutput events
        for event in _real_agent_stream(question, hf_token):
            yield event
        return
    except ImportError:
        pass
    except Exception as e:
        yield ("final", f"_Agent run failed: {e}_")
        return
    try:
        for event in _v1_agent_stream(question, skill, hf_token, selected_break):
            yield event
        return
    except Exception:
        pass
    for event in _stub_agent_stream(message, skill, selected_break):
        yield event
