"""Agent-trace parsing: payload coercion, telemetry, chart builders."""

from __future__ import annotations

import ast
import json
import re

import pandas as pd

from legacy.app.breaks_data import DF
from legacy.app.browse_sync import _records

def _coerce_scored_hours(payload) -> list[dict] | None:
    """Coerce a score_week tool_result payload to a list of scored hour dicts.

    Accepts a list of dicts directly, a JSON string, or a Python-repr
    string (``str(list)`` as captured by the wavereader trace), plus a
    ``{"scored": [...]}`` wrapper (as an object or a JSON string of one —
    trace observations are strings). Also accepts the
    ``{"windows": [...]}`` slim shape from ``find_best_windows``.
    Returns None when not scorable.
    """
    if isinstance(payload, dict) and isinstance(payload.get("scored"), list):
        payload = payload["scored"]
    if isinstance(payload, dict) and isinstance(payload.get("windows"), list):
        payload = payload["windows"]
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            try:
                payload = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
        if isinstance(payload, dict) and isinstance(payload.get("scored"), list):
            payload = payload["scored"]
    if not isinstance(payload, list) or not payload:
        return None
    if not all(isinstance(r, dict) and "score" in r and "time" in r for r in payload):
        return None
    return payload


def _agent_scored_hours(trace) -> list[dict] | None:
    """Return the LAST score_week tool_result payload from an agent trace.

    Charts are built from this deterministic payload — the LLM never owns
    numbers. Returns None when the run surfaced no scorable hours.
    """
    events = list(getattr(trace, "events", None) or [])
    for ev in reversed(events):
        if getattr(ev, "type", None) != "tool_result":
            continue
        data = getattr(ev, "data", None) or {}
        if data.get("name") != "score_week":
            continue
        payload = data.get("observation")
        if payload is None:
            payload = data.get("payload", data.get("result"))
        hours = _coerce_scored_hours(payload)
        if hours:
            return hours
    return None


def _agent_score_spot_ref(trace) -> tuple[str | None, str | None]:
    """Return (spot_name, region) from the last score_week tool_call, if any."""
    events = list(getattr(trace, "events", None) or [])
    for ev in reversed(events):
        if getattr(ev, "type", None) != "tool_call":
            continue
        data = getattr(ev, "data", None) or {}
        if data.get("name") != "score_week":
            continue
        args = data.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except (json.JSONDecodeError, ValueError):
                args = {}
        if isinstance(args, dict):
            return args.get("spot_name"), args.get("region")
        return None, None
    return None, None


def _coerce_rank_rows(payload) -> list[dict] | None:
    """Coerce a rank/sweep tool_result payload to a row list.

    Accepts a list of dicts directly, a JSON string, or a Python-repr
    string (``str(list)`` as captured by the wavereader trace), plus a
    ``{"rank": [...]}`` wrapper or a ``{"spots": [...]}`` region-sweep
    wrapper (score_region_week rows carry the same name/best_score keys)
    as an object or JSON string. Returns None when not a rank payload.
    """
    if isinstance(payload, dict) and isinstance(payload.get("rank"), list):
        payload = payload["rank"]
    if isinstance(payload, dict) and isinstance(payload.get("spots"), list):
        payload = payload["spots"]
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            try:
                payload = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
        if isinstance(payload, dict) and isinstance(payload.get("rank"), list):
            payload = payload["rank"]
        if isinstance(payload, dict) and isinstance(payload.get("spots"), list):
            payload = payload["spots"]
    if not isinstance(payload, list) or not payload:
        return None
    if not all(
        isinstance(r, dict) and "name" in r and "best_score" in r for r in payload
    ):
        return None
    return payload


def _parse_tool_args(data: dict) -> dict:
    """Return the arguments dict from a tool_call event payload."""
    args = data.get("arguments", data.get("args", {}))
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, ValueError):
            return {}
    return args if isinstance(args, dict) else {}


def _result_payload(data: dict):
    """Return the observation payload from a tool_result event payload."""
    payload = data.get("observation")
    if payload is None:
        payload = data.get("payload", data.get("result"))
    return payload


def _agent_chart_data(trace) -> dict:
    """Collect ALL score_week + get_forecast payloads + rank payload.

    Returns ``{"spots": [...], "forecasts": [...], "rank": [...] | None}``
    where each spot is ``{"label": str, "spot_name": str | None,
    "region": str | None, "hours": [...]}`` and each forecast entry is
    ``{"label": str, "spot_name": ..., "region": ..., "hours": [...]}``
    with swell/wind-chartable (unscored) hours. Handles both the new
    ``{"scored": [...]}`` dict shape and the legacy list shape via
    :func:`_coerce_scored_hours`. Score calls are paired with their
    tool_call args in FIFO order so each chart is labelled with the spot
    the agent actually scored; forecast calls pair the same way via
    :func:`_coerce_forecast_hours`.
    """
    spots: list[dict] = []
    forecasts: list[dict] = []
    rank: list[dict] | None = None
    events = list(getattr(trace, "events", None) or [])
    pending: list[tuple[str | None, str | None, str | None]] = []
    pending_fc: list[tuple[str | None, str | None]] = []
    for ev in events:
        ev_type = getattr(ev, "type", None)
        data = getattr(ev, "data", None) or {}
        if ev_type in ("tool_call", "tool_start", "tool"):
            name = data.get("name")
            if name in ("score_week", "find_best_windows"):
                args = _parse_tool_args(data)
                pending.append(
                    (args.get("spot_name"), args.get("region"), args.get("skill"))
                )
            elif name == "get_forecast":
                args = _parse_tool_args(data)
                pending_fc.append((args.get("spot_name"), args.get("region")))
        elif ev_type in ("tool_result", "tool_end"):
            name = data.get("name")
            if name in ("score_week", "find_best_windows"):
                raw = _result_payload(data)
                hours = _coerce_scored_hours(raw)
                if not hours:
                    continue
                if pending:
                    spot_name, region, skill_arg = pending.pop(0)
                else:
                    spot_name, region, skill_arg = None, None, None
                skill_val = skill_arg
                if isinstance(raw, dict):
                    spot_info = raw.get("spot") or {}
                    spot_name = spot_name or spot_info.get("name")
                    region = region or spot_info.get("region") or spot_info.get(
                        "state"
                    )
                    skill_val = raw.get("skill") or skill_val
                if spot_name:
                    label = (
                        f"{spot_name} ({region})"
                        if region
                        else str(spot_name)
                    )
                else:
                    label = f"spot {len(spots) + 1}"
                spots.append(
                    {
                        "label": label,
                        "spot_name": spot_name,
                        "region": region,
                        "skill": skill_val,
                        "hours": hours,
                    }
                )
            elif name == "get_forecast":
                raw = _result_payload(data)
                if isinstance(raw, dict) and "error" in raw:
                    if pending_fc:
                        pending_fc.pop(0)
                    continue
                hours = _coerce_forecast_hours(raw)
                if not hours:
                    continue
                if pending_fc:
                    spot_name, region = pending_fc.pop(0)
                else:
                    spot_name, region = None, None
                if spot_name:
                    label = (
                        f"{spot_name} ({region})"
                        if region
                        else str(spot_name)
                    )
                else:
                    label = f"forecast {len(forecasts) + 1}"
                forecasts.append(
                    {
                        "label": label,
                        "spot_name": spot_name,
                        "region": region,
                        "hours": hours,
                    }
                )
            elif name in ("rank_spots_this_week", "score_region_week"):
                rows = _coerce_rank_rows(_result_payload(data))
                if rows:
                    rank = rows
    # Deduplicate labels so the dropdown stays unambiguous.
    seen: dict[str, int] = {}
    for spot in spots:
        label = spot["label"]
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            spot["label"] = f"{label} #{seen[label]}"
    for entry in forecasts:
        label = entry["label"]
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            entry["label"] = f"{label} #{seen[label]}"
    return {"spots": spots, "forecasts": forecasts, "rank": rank}


def _format_rank_table(rank: list[dict] | None) -> pd.DataFrame:
    """Format a rank/sweep payload as a leaderboard dataframe."""
    if not rank:
        return pd.DataFrame(columns=["Rank", "Spot", "Region", "Best score", "Best time"])
    rows = [
        (
            i + 1,
            r.get("name", "?"),
            r.get("region", "?"),
            r.get("best_score", ""),
            r.get("best_time", ""),
        )
        for i, r in enumerate(rank)
    ]
    return pd.DataFrame(
        rows, columns=["Rank", "Spot", "Region", "Best score", "Best time"]
    )


def _short_args(args: dict, limit: int = 160) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _summarize_result(name: str | None, payload) -> str:
    """One-line summary of a tool_result observation for telemetry."""
    if name == "score_week":
        hours = _coerce_scored_hours(payload)
        if hours:
            if isinstance(payload, dict):
                spot = payload.get("spot") or {}
                label = spot.get("name")
                skill = payload.get("skill")
                if label:
                    return (
                        f"{len(hours)} scored hour(s) for {label}"
                        + (f" ({skill})" if skill else "")
                    )
            return f"{len(hours)} scored hour(s)"
    if name in ("rank_spots_this_week", "score_region_week"):
        rows = _coerce_rank_rows(payload)
        if rows:
            top = rows[0]
            verb = "swept" if name == "score_region_week" else "ranked"
            extra = ""
            if name == "score_region_week" and isinstance(payload, dict):
                extra = f" in {payload.get('region', '?')}"
                if payload.get("coverage_note"):
                    extra += " (partial coverage)"
            return (
                f"{len(rows)} spot(s) {verb}{extra} "
                f"(top: {top.get('name', '?')} {top.get('best_score', '?')}/10)"
            )
        if name == "score_region_week" and isinstance(payload, dict):
            return f"0 spots swept in {payload.get('region', '?')} (no matches)"
    if name == "get_forecast":
        hours = _coerce_forecast_hours(payload)
        if hours:
            return f"{len(hours)} forecast hour(s) (swell + wind)"
    if name == "find_best_windows":
        wins = None
        if isinstance(payload, dict):
            wins = payload.get("windows")
        if isinstance(wins, list) and wins:
            top = wins[0]
            return (
                f"{len(wins)} window(s) "
                f"(top: {top.get('time', '?')} {top.get('score', '?')}/10)"
            )
        return "filtered windows"
    if name == "explain_score_breakdown":
        if isinstance(payload, dict) and "components" in payload:
            return (
                f"breakdown {payload.get('time', '?')} "
                f"{payload.get('score', '?')}/10 {payload.get('components')}"
            )[:140]
    if name == "get_spot_sun_sst":
        if isinstance(payload, dict):
            bits = []
            if payload.get("sea_surface_temp_c") is not None:
                bits.append(f"SST {payload.get('sea_surface_temp_c')}C")
            if payload.get("wetsuit_hint"):
                bits.append(str(payload.get("wetsuit_hint")))
            return "; ".join(bits)[:140] or "sun + SST"
    if name == "find_similar_spots":
        if isinstance(payload, list) and payload:
            return (
                f"{len(payload)} similar spot(s) "
                f"(top: {payload[0].get('name', '?')})"
            )
    if name == "list_states_regions":
        if isinstance(payload, dict) and "states" in payload:
            return f"{len(payload['states'])} states vocab"
    if isinstance(payload, str):
        text = payload.strip()
        if len(text) > 140:
            return f"{len(text)} chars: {text[:139]}…"
        return f"{len(text)} chars" if len(text) > 60 else text or "(empty)"
    if isinstance(payload, list):
        return f"{len(payload)} row(s)"
    if isinstance(payload, dict):
        if "error" in payload:
            return f"error: {payload.get('error')}"
        return f"keys={sorted(payload.keys())}"
    return str(payload)[:140] if payload is not None else "(empty)"


def _build_agent_telemetry(trace, tool_count: int = 0) -> list[str]:
    """Rich telemetry lines from trace events: args, duration, summaries.

    Handles ``tool_call``/``tool_start`` (+ legacy ``tool``) starts and
    ``tool_result``/``tool_end`` ends, pairing them by event id when
    present and FIFO by tool name otherwise.
    """
    lines: list[str] = []
    events = list(getattr(trace, "events", None) or [])
    pending_by_id: dict[str, tuple[str, dict, float]] = {}
    pending_fifo: list[tuple[str, dict, float]] = []
    for ev in events:
        ev_type = getattr(ev, "type", None)
        data = getattr(ev, "data", None) or {}
        ts = float(getattr(ev, "timestamp", 0) or 0)
        if ev_type in ("tool_call", "tool_start", "tool"):
            name = str(data.get("name", "?"))
            args = _parse_tool_args(data)
            tid = data.get("id")
            if tid is not None:
                pending_by_id[str(tid)] = (name, args, ts)
            else:
                pending_fifo.append((name, args, ts))
            lines.append(f"🔧 [tool: {name}] args={_short_args(args)}")
        elif ev_type in ("tool_result", "tool_end"):
            name = str(data.get("name", "?"))
            payload = _result_payload(data)
            summary = _summarize_result(name, payload)
            tid = data.get("id")
            t0: float | None = None
            if tid is not None and str(tid) in pending_by_id:
                _, _, t0 = pending_by_id.pop(str(tid))
            elif pending_fifo:
                queued_name, _, queued_t0 = pending_fifo[0]
                if queued_name == name or queued_name == "?":
                    _, _, t0 = pending_fifo.pop(0)
            if t0 and ts and ts >= t0:
                lines.append(f"📦 [{name}] done in {ts - t0:.1f}s → {summary}")
            else:
                lines.append(f"📦 [{name}] → {summary}")
        elif ev_type == "error":
            lines.append(f"❌ {data.get('error', data)}")
    if tool_count and not lines:
        lines.append(f"ℹ️ {tool_count} tool call(s) ran (no trace details).")
    return lines


def _match_break_by_name(name: str | None) -> dict | None:
    """Find an enriched break record by name (case-insensitive)."""
    if not name:
        return None
    want = str(name).strip().lower()
    for record in _records(DF):
        if str(record.get("name", "")).strip().lower() == want:
            return record
    return None


def _agent_chart_spot(selected_break: dict | None, trace, forecast_mod):
    """Resolve the scoring spot for the agent-tab wind chart.

    Prefers the break the agent actually scored (matched from the
    score_week tool_call back to the enriched list), falling back to the
    encyclopedia ``selected_break``. Returns None when neither resolves —
    the wind fig then renders without directional colouring.
    """
    to_spot = forecast_mod.enriched_to_scoring_spot
    spot_name, _region = _agent_score_spot_ref(trace)
    match = _match_break_by_name(spot_name)
    if match is not None:
        return to_spot(match)
    if selected_break:
        return to_spot(selected_break)
    return None


def _format_agent_best(
    best: dict | None, label: str | None = None, skill: str | None = None
) -> str:
    """Format a best_window() hour as markdown (same shape as forecast tab).

    ``label``/``skill`` suffix keeps agent-tab headers identical to the
    forecast tab's ``best_md`` context (spot + skill) whenever known.
    """
    if not best:
        return "_No scored hours in this window._"
    base = (
        f"**{best.get('score')}/10 @ {best.get('time')}** — "
        f"{best.get('wave_height_m')}m @ {best.get('wave_period_s')}s, "
        f"wind {best.get('wind_speed_kt')}kt "
        f"({best.get('wind_direction_deg')}°)"
    )
    suffix_bits = [b for b in (label, skill) if b]
    if suffix_bits:
        base += f" · _{' · '.join(suffix_bits)}_"
    return base


_CODE_CALL_RE = re.compile(r"([A-Za-z_]\w*)\s*\(([^()]*)\)")


_NON_TOOL_CALLS = frozenset({"print", "final_answer", "len", "str", "float", "int", "round"})


def _parse_code_calls(code: str) -> list[str]:
    """Parse executed agent code into short chat-friendly tool lines.

    Strips assignments/``print(...)`` wrappers, drops non-tool calls,
    and truncates long arg lists. E.g.
    ``win2 = find_best_windows(spot_name="X", ...)`` →
    ``🔧 find_best_windows(spot_name="X", …)``.
    """
    lines: list[str] = []
    for func, args in _CODE_CALL_RE.findall(code or ""):
        if func in _NON_TOOL_CALLS:
            continue
        args = " ".join(args.split())
        if len(args) > 140:
            args = args[:139] + "…"
        lines.append(f"🔧 `{func}({args})`")
    return lines


def _human_tool_status(name: str | None, args: dict) -> str:
    """Human-readable activity line for a tool_start event.

    Turns raw calls into e.g. ``Scoring Bells Beach for intermediate…``
    so the status box reads as progress while the tool loads.
    """
    args = args or {}
    spot = args.get("spot_name") or args.get("spot") or args.get("query")
    region = args.get("region")
    skill = args.get("skill")
    if name == "score_week":
        what = f"Scoring {spot or 'spot'}" + (f" ({region})" if region else "")
        if skill:
            what += f" for {skill}"
        return f"{what}…"
    if name == "get_forecast":
        what = f"Fetching forecast for {spot or 'spot'}"
        if region:
            what += f" ({region})"
        return f"{what}…"
    if name == "rank_spots_this_week":
        return f"Ranking spots in {region or 'region'}" + (
            f" for {skill}…" if skill else "…"
        )
    if name == "score_region_week":
        extra = " (weekend)" if args.get("weekend_only") else ""
        return f"Sweeping {region or 'region'}{extra}" + (
            f" for {skill}…" if skill else "…"
        )
    if name == "get_spot_knowledge":
        return f"Looking up {spot or 'spot'}" + (
            f" ({region})…" if region else "…"
        )
    if name == "find_spots":
        q = args.get("query") or region or ""
        return f"Searching breaks for '{q or '…'}'" + (
            f" ({skill})…" if skill else "…"
        )
    if name == "find_best_windows":
        spot = args.get("spot_name") or args.get("spot")
        part = args.get("daypart") or "all"
        extra = " (weekend)" if args.get("weekend_only") else ""
        return f"Finding best {part} windows for {spot or 'spot'}{extra}…"
    if name == "explain_score_breakdown":
        spot = args.get("spot_name") or args.get("spot")
        return f"Explaining score for {spot or 'spot'}…"
    if name == "get_spot_sun_sst":
        spot = args.get("spot_name") or args.get("spot")
        return f"Checking sun + water temp for {spot or 'spot'}…"
    if name == "find_similar_spots":
        spot = args.get("spot_name") or args.get("spot")
        return f"Finding breaks like {spot or 'spot'}…"
    if name == "list_states_regions":
        return "Listing states + regions…"
    return f"Running {name or 'tool'}…"


def _live_spot_label(spot_name: str | None, region: str | None, idx: int) -> str:
    """Label a progressively-charted spot (mirrors _agent_chart_data)."""
    if spot_name:
        return f"{spot_name} ({region})" if region else str(spot_name)
    return f"spot {idx}"


def _dedupe_spot_labels(spots: list[dict]) -> None:
    """Append ``#N`` suffixes so live dropdown labels stay unambiguous."""
    seen: dict[str, int] = {}
    for spot in spots:
        label = spot.get("label", "?")
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            spot["label"] = f"{label} #{seen[label]}"


def _resolve_spot_for_entry(
    entry: dict | None, selected_break: dict | None, forecast_mod
):
    """Resolve the scoring spot for wind directional colouring.

    Prefers the break the agent actually scored (matched by name back to
    the enriched list), falling back to the encyclopedia ``selected_break``.
    Single place both the final and progressive chart paths use.
    """
    to_spot = forecast_mod.enriched_to_scoring_spot
    match = _match_break_by_name((entry or {}).get("spot_name"))
    if match is not None:
        return to_spot(match)
    if selected_break:
        return to_spot(selected_break)
    return None


def _build_chart_trio(
    hours: list[dict], spot, label: str | None = None, skill: str | None = None
):
    """Build score/swell/wind figs + best markdown with one shared style.

    Same builders, same heights/titles/empty states in the forecast tab,
    the agent-tab final render, progressive updates, and the spot dropdown.
    """
    from legacy.app import surf_forecast as mod
    score_fig = mod.build_score_fig(hours)
    waves_fig = mod.build_waves_fig(hours)
    wind_fig = mod.build_wind_fig(hours, spot)
    best_md = _format_agent_best(mod.best_window(hours), label, skill)
    return score_fig, waves_fig, wind_fig, best_md


def _coerce_forecast_hours(payload) -> list[dict] | None:
    """Coerce a get_forecast frame to chartable swell/wind hour dicts.

    Accepts the raw ``{"hourly": [...]}`` frame (or a JSON/Python-repr
    string of one). Each row is mapped to the scored-hour key shape the
    swell/wind builders read (``wave_height_m``, ``wave_period_s``,
    ``wind_speed_kt``, ``wind_direction_deg``, ``time``) so an unscored
    forecast still outputs its swell + wind graphs. Returns None when
    no chartable rows exist.
    """
    if isinstance(payload, dict) and isinstance(payload.get("hourly"), list):
        rows = payload["hourly"]
    elif isinstance(payload, str):
        text = payload.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            try:
                parsed = ast.literal_eval(text)
            except (ValueError, SyntaxError):
                return None
        if isinstance(parsed, dict) and isinstance(parsed.get("hourly"), list):
            rows = parsed["hourly"]
        elif isinstance(parsed, list):
            rows = parsed
        else:
            return None
    elif isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        return None
    else:
        return None
    if not isinstance(rows, list) or not rows:
        return None
    hours: list[dict] = []
    for r in rows:
        if not isinstance(r, dict) or "time" not in r:
            continue
        try:
            wave_h = r.get("wave_height", r.get("wave_height_m"))
            period = r.get("wave_period", r.get("wave_period_s"))
            wind_spd = r.get("wind_speed_10m")
            if wind_spd is None:
                wind_spd = r.get("wind_speed_kt")
                wind_kt = float(wind_spd) if wind_spd is not None else None
            else:
                wind_kt = float(wind_spd) * 0.539957  # km/h -> kt
            wind_dir = r.get("wind_direction_10m", r.get("wind_direction_deg"))
            if wave_h is None or period is None or wind_kt is None or wind_dir is None:
                continue
            hours.append(
                {
                    "time": r.get("time"),
                    "wave_height_m": float(wave_h),
                    "wave_period_s": float(period),
                    "wave_direction_deg": (
                        float(r.get("wave_direction"))
                        if r.get("wave_direction") is not None
                        else None
                    ),
                    "wind_speed_kt": round(wind_kt, 1),
                    "wind_direction_deg": float(wind_dir),
                }
            )
        except (TypeError, ValueError):
            continue
    return hours or None


def _format_forecast_best(hours: list[dict], label: str | None = None) -> str:
    """One-line swell/wind summary for an unscored forecast (no scores)."""
    if not hours:
        return "_No forecast hours in this window._"
    try:
        peak = max(hours, key=lambda r: float(r.get("wave_height_m") or 0))
        calm = min(hours, key=lambda r: float(r.get("wind_speed_kt") or 0))
        base = (
            f"**Peak {peak.get('wave_height_m')}m @ {peak.get('wave_period_s')}s "
            f"({peak.get('time')})** — "
            f"lightest wind {calm.get('wind_speed_kt')}kt @ {calm.get('time')}"
        )
    except (TypeError, ValueError, KeyError):
        base = f"**{len(hours)} forecast hour(s)**"
        peak = None
    if label:
        base += f" · _{label}_ (unscored forecast — no score chart)"
    return base


def _build_forecast_duo(hours: list[dict], spot, label: str | None = None):
    """Build swell + wind figs + summary for a raw get_forecast frame.

    No score fig exists without scoring — callers must pass
    ``gr.skip()`` for the score output so the current score chart is kept.
    """
    from legacy.app import surf_forecast as mod
    waves_fig = mod.build_waves_fig(hours)
    wind_fig = mod.build_wind_fig(hours, spot)
    best_md = _format_forecast_best(hours, label)
    return waves_fig, wind_fig, best_md
