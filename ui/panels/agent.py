"""Agent panel: live tool-trace feed, budget meter, verdict banner, charts.

Consumes typed v2 agent events (``token | step | tool_call | tool_result |
final | usage``) from :func:`ui._compat.agent_run_stream`. Every tool call
renders as a trace card — pending while running, then done with a wall-time
ms bar scaled to the slowest call this turn and an expandable payload
preview. The budget meter ticks live (steps / tool calls / score_week cap /
≈tokens) against the slider-chosen tool budget, and the final answer's
"Best: …" contract line is lifted into a verdict banner. Any ``score_week``
payload in a tool result is charted straight into the week strip (the LLM
never owns numbers), and **every answered turn ends with a visualisation
matched to the question**: recommendation questions close on the
recommended-scores chart — a region-sweep leaderboard, or a side-by-side
compare when several spots were scored this turn (a deterministic engine
sweep fills in when the agent never ranked); climate / seafloor / similar /
explain questions get their rose, depth map, similarity bars or component
split; anything else falls back to the viewed spot's own scored week.

User controls in the bar: a "max tool calls" slider (the per-turn step
budget; token + score_week caps scale with it) and chained State → Region
dropdowns — page-one style, the State pick rewrites the Region choices —
that anchor "where should I surf" sweeps. Both are plain component inputs —
session state stays at exactly three ``gr.State`` objects. Skill comes
from the lens panel's Skill filter — one skill, whole page.

The BYO HF token box is session-only: the value is passed straight to the
agent factory per turn, never stored, never logged.
"""

from __future__ import annotations

import html
import json
import re

import gradio as gr

from ui import _compat as C
from ui.charts import climate as climate_chart
from ui.charts import seafloor as seafloor_chart
from ui.charts import score as score_chart
from ui.charts import strip as strip_chart
from ui.contracts import AGENT_KEYS, fill

_TOOL_ICONS = {
    "score_week": "⚙", "rank_region_week": "🏆", "explain_score": "🔍",
    "find_best_windows": "🕐", "find_spots": "🔎", "find_similar_spots": "🧭",
    "get_spot_knowledge": "📖", "get_climate_profile": "🌡",
    "get_seafloor_profile": "🪨", "get_session_brief": "🤿",
    "list_regions": "🗺",
}
_MEDALS = ["🥇", "🥈", "🥉"]
_VERDICT_RE = re.compile(r"Best:\s*(.+)", re.IGNORECASE)

# Query intent (deterministic, on the user's text only): which end-of-turn
# chart matches the question. Scores charts are the house default; the
# specialties jump the queue only when the question asks for them.
_REC_RE = re.compile(
    r"\bwhere\s+(?:should|to|can|shall|could)\b"
    r"|\bbest\s+(?:spots?|breaks?|beaches?|places?)\b"
    r"|\brecommend|\brank\w*|\btop\s*\d+"
    r"|\bcompare|\bversus\b|\bvs\b"
    r"|\bshould\s+i\s+(?:surf|go|paddle)\b", re.IGNORECASE)
_CLIMATE_RE = re.compile(
    r"\bclimate\b|\bmonthly\b|\bmonths?\b|winter|summer|autumn|spring\b"
    r"|\bswell\s+direction\b|\bwhen\s+to\s+go\b", re.IGNORECASE)
_SEAFLOOR_RE = re.compile(
    r"\bseafloor\b|\bsea\s?floor\b|\bsea\s?bed\b|\bbathymetry\b|\bdepths?\b"
    r"|\bstructure\b|\bsandbar\b|\breef\b", re.IGNORECASE)
_SIMILAR_RE = re.compile(
    r"\b(?:spots?|breaks?|beaches?)\s+like\b|\bsimilar\s+to\b"
    r"|\balternatives?\s+to\b|\bquieter\b", re.IGNORECASE)
_EXPLAIN_RE = re.compile(
    r"\bwhy\b|\bexplain\w*|\bcomponent\w*|\bbreakdown\b", re.IGNORECASE)
_SPECIALTY_RE = (
    ("get_climate_profile", _CLIMATE_RE),
    ("get_seafloor_profile", _SEAFLOOR_RE),
    ("find_similar_spots", _SIMILAR_RE),
    ("explain_score", _EXPLAIN_RE),
)
_STATE_CODES = {
    "NSW": "New South Wales", "QLD": "Queensland", "VIC": "Victoria",
    "WA": "Western Australia", "SA": "South Australia", "TAS": "Tasmania",
}

_EMPTY_TRACE = ("<div class='trace-empty'>tool calls land here live — "
                "watch the engines work…</div>")
_EMPTY_RANK_HTML = ("<div class='rank-empty'>leaderboard — ask "
                    "“where should I surf in …” to rank a region.</div>")


def _short_args(args: dict, limit: int = 120) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _pretty_time(value) -> str:
    text = str(value or "")
    return text.replace("T", " ")[:16]


def _trace_html(cards: list[dict], ask: str = "") -> str:
    """Render the live tool trace: cards + timing bars + payload previews."""
    bits = []
    if ask:
        bits.append(f"<div class='trace-ask'>ask: {html.escape(ask[:140])}</div>")
    if not cards:
        bits.append(_EMPTY_TRACE)
        return "".join(bits) if ask else _EMPTY_TRACE
    times = [c.get("ms") for c in cards
             if c.get("state") == "done" and isinstance(c.get("ms"), (int, float))]
    slowest = max(times) if times else 0.0
    parts = list(bits)
    parts.append("<div class='trace'>")
    for c in cards:
        icon = _TOOL_ICONS.get(str(c.get("name")), "🔧")
        done = c.get("state") == "done"
        state_cls = "done" if done else "pending"
        ms = c.get("ms")
        ms_bit = ("<span class='trace-ms'>…running</span>" if not done
                  else f"<span class='trace-ms'>⚡ {float(ms):.0f} ms</span>"
                  if isinstance(ms, (int, float))
                  else "<span class='trace-ms'>done</span>")
        bar = ""
        if done and isinstance(ms, (int, float)) and slowest > 0:
            pct = max(6, int(round(100.0 * float(ms) / slowest)))
            bar = f"<div class='trace-bar'><i style='width:{pct}%'></i></div>"
        summary = (f"<div class='trace-summary'>{html.escape(str(c.get('summary') or ''))}</div>"
                   if done and c.get("summary") else "")
        details = ""
        if done and c.get("preview"):
            details = ("<details><summary>payload</summary>"
                       f"<pre>{html.escape(str(c['preview']))}</pre></details>")
        parts.append(
            f"<div class='trace-card {state_cls}'>"
            "<div class='trace-head'>"
            f"<span class='trace-icon'>{icon}</span>"
            f"<code>{html.escape(str(c.get('name', '?')))}"
            f"({html.escape(str(c.get('args', '')))})</code>"
            f"{ms_bit}</div>{bar}{summary}{details}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _verdict_html(text: str) -> str:
    """Lift the answer's contract verdict line ("Best: …") into a banner."""
    for line in (text or "").splitlines():
        match = _VERDICT_RE.search(line)
        if match:
            clean = re.sub(r"\*", "", match.group(1)).strip()
            if clean:
                return (f"<div class='verdict-banner'>🏆 <b>Best:</b> "
                        f"{html.escape(clean)}</div>")
    return ""


def _format_rank_cards(rank: list[dict] | None) -> str:
    if not rank:
        return _EMPTY_RANK_HTML
    parts = ["<div class='rank-list'>"]
    for i, r in enumerate(rank):
        medal = _MEDALS[i] if i < len(_MEDALS) else str(i + 1)
        score = r.get("best_score", "")
        score_bit = f"{score}/10" if score not in ("", None) else "—"
        parts.append(
            "<div class='rank-card'>"
            f"<span class='rank-num'>{medal}</span>"
            "<span class='rank-name'>"
            f"<b>{html.escape(str(r.get('name', '?')))}</b> "
            f"<i>{html.escape(str(r.get('region', '') or ''))}</i></span>"
            f"<span class='rank-score'>{html.escape(score_bit)}</span>"
            f"<span class='rank-time'>{html.escape(_pretty_time(r.get('best_time')))}</span>"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _format_meter(usage: dict | None, source: str,
                  caps: dict | None = None) -> str:
    """Final meter after a turn: exact tokens (when known) + steps + caps."""
    if not usage:
        return "_Token meter — per-turn usage lands here._"
    model = str(usage.get("model") or "").split("/")[-1]
    profile = usage.get("profile")
    budget = usage.get("budget") or caps or {}
    tail = (f" · {profile} profile" if profile else "") \
        + (f" · cap {budget.get('max_steps', '?')} steps" if budget else "") \
        + (f" · {model}" if model else "") + f" (via {source})"
    if usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None:
        p = usage.get("prompt_tokens", "?")
        c = usage.get("completion_tokens", "?")
        try:
            total = int(p) + int(c)
        except (TypeError, ValueError):
            total = "?"
        return f"🪙 **prompt {p} · completion {c} · total {total} tokens**{tail}"
    steps = usage.get("steps", "?")
    calls = usage.get("tool_calls") or {}
    n_calls = sum(calls.values()) if isinstance(calls, dict) else "?"
    return f"⚙️ **{steps} steps · {n_calls} tool call(s)**{tail}"


def _live_meter(live: dict, caps: dict, source: str) -> str:
    """Mid-turn meter: running counts against the depth profile's caps."""
    bits = [
        f"⚙️ steps {live.get('steps', 0)}/{caps.get('max_steps', '?')}",
        f"🔧 {live.get('calls', 0)} call(s)",
        f"score_week {live.get('score_week', 0)}/{caps.get('score_week_calls', '?')}",
        f"≈{live.get('chars', 0) // 4} tokens",
    ]
    return " · ".join(bits) + f" — _via {source}_"


def fresh_store() -> dict:
    return {"spots": [], "rank": None, "usage": None}


def _build_strip(hours: list[dict], label: str, records: list[dict]):
    """Week strip + best-hour line for an agent-scored spot."""
    spot_name = label.split(" (")[0]
    match = C.find_break(records, spot_name)
    fig = strip_chart.build_week_strip(hours, _scoring_spot(match), height=520)
    return fig, score_chart.format_best(score_chart.best_window(hours), label)


def _scoring_spot(break_: dict | None) -> dict | None:
    """Minimal scoring spot for wind directional colouring."""
    if not break_:
        return None
    wind = (break_ or {}).get("idealWind", {}) or {}
    direction = wind.get("direction", "N")
    if isinstance(direction, list):
        direction = "/".join(str(d) for d in direction if d)
    return {"ideal_wind": {"direction": str(direction or "N")}}


def _coerce_rank_rows(payload) -> list[dict] | None:
    if isinstance(payload, dict) and isinstance(payload.get("rank"), list):
        payload = payload["rank"]
    if isinstance(payload, dict) and isinstance(payload.get("spots"), list):
        payload = payload["spots"]
    if not isinstance(payload, list) or not payload:
        return None
    if not all(isinstance(r, dict) and "name" in r and "best_score" in r for r in payload):
        return None
    return payload


def _viz_spot(args: dict, obs) -> tuple[str, str]:
    """(name, region) for a tool observation, falling back to call args."""
    info = (obs.get("spot") or {}) if isinstance(obs, dict) else {}
    name = args.get("spot_name") or info.get("name") or ""
    region = args.get("region") or info.get("region") or ""
    return str(name), str(region)


def _specialty_tool(query: str) -> str | None:
    """The tool whose chart the question explicitly asks for, if any."""
    for tool_name, rx in _SPECIALTY_RE:
        if rx.search(query or ""):
            return tool_name
    return None


def _rose_chart(entry: tuple[dict, object], records: list[dict]):
    _a, obs = entry
    if not isinstance(obs, dict):
        return None, ""
    rose = (obs.get("climate") or {}).get("direction_rose_pct") or {}
    try:
        if not any(float(v or 0) > 0 for v in rose.values()):
            return None, ""
    except (TypeError, ValueError):
        return None, ""
    name, _region = _viz_spot(_a, obs)
    rec = C.find_break(records, name)
    ideal = (((rec or {}).get("idealSwell") or {}).get("direction")
             if rec else None)
    fig = climate_chart.build_rose_fig({"rose": rose}, name=name,
                                       ideal_dirs=ideal)
    return fig, f"swell climate — {name} (5-yr ERA5 rose)"


def _depth_chart(entry: tuple[dict, object], records: list[dict]):
    _a, obs = entry
    if not isinstance(obs, dict):
        return None, ""
    name, _region = _viz_spot(_a, obs)
    rec = C.find_break(records, name)
    if not rec:
        return None, ""
    try:
        grid = (C.get_seafloor(rec) or {}).get("grid") or {}
        return seafloor_chart.build_depth_fig(grid, name), \
            f"seafloor depth map — {name}"
    except Exception:  # noqa: BLE001 — fall through to the next viz
        return None, ""


def _similarity_chart(entry: tuple[dict, object], records: list[dict]):
    _a, obs = entry
    if (isinstance(obs, list) and obs and isinstance(obs[0], dict)
            and "similarity" in obs[0]):
        ref = str(_a.get("spot_name") or "")
        return (score_chart.build_similarity_fig(obs, ref),
                f"{len(obs)} spots like {ref} — similarity")
    return None, ""


def _components_chart(entry: tuple[dict, object], records: list[dict]):
    _a, obs = entry
    if (isinstance(obs, dict) and isinstance(obs.get("components"), dict)
            and obs["components"]):
        name, _region = _viz_spot(_a, obs)
        when = str(obs.get("time") or "")
        fig = score_chart.build_component_fig(obs["components"], spot=name,
                                              when=when, score=obs.get("score"))
        return fig, f"component split — {name} @ {when}"
    return None, ""


def _specialty_figure(by_name: dict[str, tuple[dict, object]],
                      records: list[dict],
                      prefer: str | None = None):
    """First buildable question-specific chart from the tool payloads.

    Scans climate rose → seafloor depth map → similarity bars → component
    split; a question-matched tool (``prefer``) is scanned first so e.g. a
    seafloor question wins its depth map even when a rose payload exists.
    Returns (figure, markdown note) or (None, "").
    """
    checks = (
        ("get_climate_profile", _rose_chart),
        ("get_seafloor_profile", _depth_chart),
        ("find_similar_spots", _similarity_chart),
        ("explain_score", _components_chart),
    )
    if prefer:
        checks = tuple(sorted(checks, key=lambda c: c[0] != prefer))
    for _tool_name, build in checks:
        fig, note = build(by_name.get(_tool_name, ({}, None)), records)
        if fig is not None:
            return fig, note
    return None, ""


def _scored_compare_fig(scored: list[dict]):
    """Side-by-side best-score bars for a multi-spot scored turn."""
    rows = []
    for s in scored or []:
        best = score_chart.best_window(s.get("hours") or [])
        if not best:
            continue
        rows.append({"name": str(s.get("label") or "?"),
                     "region": str(s.get("region") or ""),
                     "best_score": best.get("score"),
                     "best_time": best.get("time")})
    if len(rows) < 2:
        return None, ""
    names = " vs ".join(r["name"].split(" (")[0] for r in rows[:2])
    fig = score_chart.build_compare_fig(
        rows, "name", "best_score", "recommended breaks — best score this week",
        sub_keys=("region", "best_time"))
    return fig, f"{names} — best-score compare ({len(rows)} spots)"


def _query_region(query: str, records: list[dict]) -> str | None:
    """A canonical state/region named in the query (codes expanded), or None."""
    text = f" {query or ''} ".lower()
    vocab = sorted({str(r.get("state") or "") for r in records}
                   | {str(r.get("region") or "") for r in records},
                   key=len, reverse=True)
    for name in vocab:
        if name and re.search(rf"(?<![a-z]){re.escape(name.lower())}(?![a-z])",
                              text):
            return name
    for code, name in _STATE_CODES.items():
        if re.search(rf"(?<![a-z]){code.lower()}(?![a-z])", text):
            return name
    return None


def _turn_figure(viz: list[tuple[str, dict, object]], selected: dict | None,
                 skill: str, records: list[dict], query: str = "",
                 focus: str | None = None, scored: list[dict] | None = None,
                 charted: bool = False):
    """Pick + build the end-of-turn chart, matched to the question.

    The house chart is the recommended-surf-break-scores view: a
    region-sweep leaderboard, or a side-by-side compare when several spots
    were scored this turn. Question-specific charts (climate rose, seafloor
    depth map, similarity bars, component split) jump the queue only when
    the question asks for them. A recommendation question the agent answered
    without any sweep still closes on one: a deterministic engine sweep of
    the region named in the question (or the page's State/Region focus).
    Numbers come from tool/engine output only, never from the answer text.
    Returns (figure, markdown note) or (None, "") when nothing chartable.
    """
    by_name: dict[str, tuple[dict, object]] = {}
    for name, args, obs in viz:
        by_name.setdefault(str(name), (args if isinstance(args, dict) else {}, obs))
    q = str(query or "")
    recommend = bool(_REC_RE.search(q))
    prefer = _specialty_tool(q)
    special = _specialty_figure(by_name, records, prefer)

    if charted:
        # Multi-spot scored turn: week strips already ran mid-turn — close
        # on the side-by-side scores, never an unrelated refetch.
        return _scored_compare_fig(scored or [])
    if not recommend and prefer and special[0] is not None:
        return special

    # scores first: the sweep leaderboard, then this turn's scored spots
    _a, obs = by_name.get("rank_region_week", ({}, None))
    rows = _coerce_rank_rows(obs)
    if rows:
        region = str((obs or {}).get("region") if isinstance(obs, dict) else "") \
            or str(_a.get("region") or "")
        top = rows[0]
        region_bit = f" — {region}" if region else ""
        note = (f"region sweep{region_bit} — top pick "
                f"**{top.get('name')}** ({top.get('best_score')}/10)")
        return score_chart.build_rank_fig(rows, region), note
    compare = _scored_compare_fig(scored or [])
    if compare[0] is not None:
        return compare

    if recommend:
        region = _query_region(q, records) or (str(focus) if focus else None)
        if region:
            try:
                rows = _coerce_rank_rows(
                    C.api_rank_region_week(region, skill=skill))
            except Exception:  # noqa: BLE001 — chart fallbacks never raise
                rows = None
            if rows:
                top = rows[0]
                return (score_chart.build_rank_fig(rows, region),
                        f"recommended breaks — {region} — top pick "
                        f"**{top.get('name')}** ({top.get('best_score')}/10)")

    if special[0] is not None:
        return special

    sel = selected or {}
    if sel.get("name"):
        payload = C.get_scored_week(sel, skill=skill, days=7)
        hours = payload.get("scored") or []
        if hours:
            label = (f"{sel.get('name')} ({sel.get('region')})"
                     if sel.get("region") else str(sel.get("name")))
            return _build_strip(hours, label, records)

    return None, ""


def chat_fn(message: str, history: list[dict] | None, skill: str,
            hf_token: str, selected: dict | None, store: dict | None,
            steps: int | None, state: str | None, region: str | None,
            records: list[dict]):
    """Stream an agent turn: trace cards + meter + verdict + charts."""
    history = list(history or [])
    store = dict(store or fresh_store())
    cards: list[dict] = []
    usage = None
    verdict = ""
    token_source = "session token" if (hf_token or "").strip() else "space secret / env"
    try:
        steps_n = max(1, int(steps)) if steps is not None else _DEFAULT_STEPS
    except (TypeError, ValueError):
        steps_n = _DEFAULT_STEPS
    caps = C.agent_budget_for_steps(steps_n)
    live = {"steps": 0, "calls": 0, "score_week": 0, "chars": 0}
    meter = _live_meter(live, caps, token_source)
    spots = list(store.get("spots") or [])
    rank = store.get("rank")
    # Chat decorations injected by tool results (chart/seafloor/brief lines).
    # The final event replaces the streamed answer, so they are kept apart
    # and re-appended after it — otherwise they'd be wiped.
    decorations: list[str] = []
    text = (message or "").strip()
    # Tool observations kept for the end-of-turn visualisation (every
    # answered turn ends with a chart), plus whether this turn already
    # charted scored hours.
    viz: list[tuple[str, dict, object]] = []
    turn_charted = False

    def emit(status, strip_fig=None, spot_update=None):
        return fill(AGENT_KEYS, chatbot=history, msg="",
                    trace_html=_trace_html(cards, ask=text), token_md=meter,
                    agent_status=status, verdict_html=verdict,
                    agent_strip=strip_fig if strip_fig is not None else gr.skip(),
                    spot_dd=spot_update if spot_update is not None else gr.skip(),
                    rank_html=_format_rank_cards(rank),
                    agent_store=dict(store, spots=spots, rank=rank, usage=usage))

    if not text:
        yield emit("⚠️ Type a question first.")
        return
    history = [*history, {"role": "user", "content": text}, {"role": "assistant", "content": ""}]
    yield emit("⏳ Agent thinking…")

    skill = C.scoring_skill(skill)
    try:
        stream = C.agent_run_stream(text, skill=skill, hf_token=hf_token or "",
                                    selected_break=selected,
                                    region_hint=_region_hint(state, region),
                                    max_steps=steps_n)
        for kind, payload in stream:
            if kind == "token":
                chunk = str(payload)
                history[-1]["content"] += chunk
                live["chars"] += len(chunk)
                meter = _live_meter(live, caps, token_source)
                yield emit("💬 Streaming answer…")
            elif kind == "step":
                try:
                    live["steps"] = max(live["steps"], int(payload.get("n", 0)))
                except (TypeError, ValueError):
                    pass
                meter = _live_meter(live, caps, token_source)
                yield emit(f"⚙️ Step {live['steps']}/{caps.get('max_steps', '?')} — thinking…")
            elif kind == "tool_call":
                d = payload if isinstance(payload, dict) else {"name": str(payload)}
                name = str(d.get("name", "?"))
                cards.append({"name": name, "args": _short_args(d.get("arguments", {})),
                              "state": "pending", "ms": None, "summary": "", "preview": ""})
                live["calls"] += 1
                if name == "score_week":
                    live["score_week"] += 1
                meter = _live_meter(live, caps, token_source)
                yield emit(f"🔧 {name} — ⚙ engines working…")
            elif kind == "tool_result":
                d = payload if isinstance(payload, dict) else {}
                name = str(d.get("name", "?"))
                for c in reversed(cards):
                    if c["state"] == "pending":
                        c["state"] = "done"
                        c["ms"] = d.get("ms")
                        c["summary"] = d.get("summary") or "done"
                        c["preview"] = (d.get("preview") or "")[:4000]
                        break
                obs = d.get("observation")
                hours = score_chart.coerce_scored_hours(obs)
                if hours:
                    args = d.get("arguments") or {}
                    spot_name = args.get("spot_name")
                    region_arg = args.get("region")
                    if isinstance(obs, dict):
                        info = obs.get("spot") or {}
                        spot_name = spot_name or info.get("name")
                        region_arg = region_arg or info.get("region")
                    label = f"{spot_name} ({region_arg})" if spot_name and region_arg else (spot_name or f"spot {len(spots) + 1}")
                    entry_skill = skill
                    if isinstance(obs, dict) and obs.get("skill"):
                        entry_skill = obs["skill"]
                    spots.append({"label": label, "hours": hours,
                                  "skill": entry_skill,
                                  "region": str(region_arg or "")})
                    # Dedupe repeated chart labels at append time ("#2", "#3", …).
                    counts: dict[str, int] = {}
                    for s in spots:
                        counts[s["label"]] = counts.get(s["label"], 0) + 1
                        if counts[s["label"]] > 1:
                            s["label"] = f"{label} #{counts[s['label']]}"
                    fig, best_md = _build_strip(hours, spots[-1]["label"], records)
                    charted = f"📊 _Charted: {spots[-1]['label']} — {best_md}_"
                    decorations.append(charted)
                    history[-1]["content"] += f"\n\n{charted}"
                    labels = [s["label"] for s in spots]
                    turn_charted = True
                    yield emit(f"📊 Charted '{spots[-1]['label']}' — agent still thinking…",
                               strip_fig=fig,
                               spot_update=gr.update(choices=labels, value=spots[-1]["label"],
                                                     visible=len(labels) > 1))
                    continue
                if isinstance(obs, (dict, list)) and not (
                        isinstance(obs, dict) and "error" in obs):
                    viz.append((name, d.get("arguments") or {}, obs))
                rows = _coerce_rank_rows(obs)
                if rows:
                    rank = rows
                    yield emit(f"🏆 Ranked {len(rows)} spot(s) — agent still thinking…")
                    continue
                if name == "get_seafloor_profile" and isinstance(obs, dict) and "error" not in obs:
                    shelf = obs.get("shelf_class") or "shape read"
                    channel = (" — deeper gutter(s) nearby" if obs.get("channel_hint")
                               else "")
                    note = f"🪨 _Seafloor: {shelf}{channel}._"
                    decorations.append(note)
                    history[-1]["content"] += f"\n\n{note}"
                elif name == "get_session_brief" and isinstance(obs, dict) and "error" not in obs:
                    wetsuit = obs.get("wetsuit") or "check the water temp"
                    sst = obs.get("sst_c")
                    sun = f" · sun {obs.get('sunrise', '')}–{obs.get('sunset', '')}"
                    note = (f"🤿 _{wetsuit}"
                            + (f" (water {sst} °C)" if sst is not None else "")
                            + sun + "_")
                    decorations.append(note)
                    history[-1]["content"] += f"\n\n{note}"
                yield emit(f"📦 {name} done — agent still thinking…")
            elif kind == "usage":
                usage = payload if isinstance(payload, dict) else None
                meter = _format_meter(usage, token_source, caps=caps)
                yield emit("🪙 Usage recorded — agent still thinking…")
            elif kind == "final":
                final_text = str(payload) if payload else history[-1]["content"]
                tail = ("\n\n" + "\n\n".join(decorations)) if decorations else ""
                history[-1]["content"] = final_text + tail
                verdict = _verdict_html(final_text)
                yield emit("✅ Answer complete.")
    except ValueError as e:
        if "HF_TOKEN" in str(e):
            history[-1]["content"] = ("_No Hugging Face token found._ Paste one in the "
                                      "**HF token** box (session-only, never logged) or set "
                                      "`HF_TOKEN`, then ask again.")
            yield emit("⚠️ No HF token — paste one above or set HF_TOKEN.")
            return
        history[-1]["content"] += f"\n\n_❌ Agent run failed: {e}_"
        yield emit(f"❌ Agent run failed: {e}")
        return
    except Exception as e:
        history[-1]["content"] += f"\n\n_❌ Agent run failed: {e}_"
        yield emit(f"❌ Agent run failed: {e}")
        return

    # Every answered turn ends with a visualisation matched to the question,
    # scores first. Multi-spot scored turns close on the side-by-side
    # compare; otherwise the chain runs only when nothing was charted
    # mid-turn. The status is yielded first so a slow fetch (e.g. a make-up
    # region sweep) reads as a staged spin-up, never a hang.
    fallback_fig = None
    viz_note = ""
    if (not turn_charted) or len(spots) > 1:
        yield emit("📊 assembling this turn's chart…")
        try:
            fallback_fig, viz_note = _turn_figure(viz, selected, skill, records,
                                                  query=text,
                                                  focus=_region_hint(state, region),
                                                  scored=spots,
                                                  charted=turn_charted)
        except Exception:  # noqa: BLE001 — a chart must never break the answer
            fallback_fig, viz_note = None, ""
        if fallback_fig is not None:
            history[-1]["content"] += f"\n\n📊 _Charted: {viz_note}_"

    labels = [s["label"] for s in spots]
    status = ("✅ Answer complete — chart updated." if fallback_fig is not None
              else "✅ Answer complete." if (spots or rank)
              else "💬 Nothing chartable this turn — pick a spot and ask again.")
    out = dict(chatbot=history, msg="",
               trace_html=_trace_html(cards, ask=text), token_md=meter,
               agent_status=status, verdict_html=verdict,
               spot_dd=gr.update(choices=labels, value=(labels[0] if labels else None),
                                 visible=len(labels) > 1),
               rank_html=_format_rank_cards(rank),
               agent_store=dict(store, spots=spots, rank=rank, usage=usage))
    if fallback_fig is not None:
        out["agent_strip"] = fallback_fig
    yield fill(AGENT_KEYS, **out)


def show_spot(label: str | None, store: dict | None, records: list[dict]):
    """Rebuild the week strip for the spot picked in the dropdown."""
    spots = (store or {}).get("spots") or []
    entry = next((s for s in spots if s.get("label") == label), None)
    if entry is None:
        return gr.skip()
    try:
        fig, _ = _build_strip(entry["hours"], entry["label"], records)
        return fig
    except Exception:
        return gr.skip()


_DEFAULT_STEPS = 6


def _region_hint(state: str | None, region: str | None) -> str | None:
    """Agent focus from the chained filters: region > state > auto (None)."""
    for value in (region, state):
        if value and value != C.ALL:
            return str(value)
    return None


def ctx_line(skill: str, selected: dict | None, steps: int | None,
             state: str | None, region: str | None) -> str:
    """One live line showing what the agent inherits from the page."""
    caps = C.agent_budget_for_steps(int(steps) if steps else _DEFAULT_STEPS)
    name = (selected or {}).get("name") or "no spot picked"
    reg = (selected or {}).get("region") or ""
    hint = _region_hint(state, region)
    focus = hint or "auto (map pick)"
    view = f"{name}" + (f" — {reg}" if reg else "")
    return (f"scoring for **{C.scoring_skill(skill)}** · viewing **{view}** · "
            f"focus **{focus}** · budget **{caps['max_steps']} steps / "
            f"{caps['score_week_calls']} score_week / {caps['max_tokens']} tokens**")


def clear_chat():
    """Reset the agent panel (session token box is a component, untouched)."""
    return fill(AGENT_KEYS, chatbot=[], msg="",
                trace_html=_trace_html([]), token_md="_Token meter — per-turn usage lands here._",
                agent_status="Ask anything — every answer lands with a chart…",
                verdict_html="",
                agent_strip=None,
                spot_dd=gr.update(choices=[], value=None, visible=False),
                rank_html=_EMPTY_RANK_HTML, agent_store=fresh_store())


CHIP_PROMPTS = [
    "Where should I surf in NSW this weekend as a beginner?",
    "When are the best morning windows at Bells Beach this week?",
    "Compare Bells Beach and Snapper Rocks this weekend.",
    "What's the seafloor like at Bells Beach — and what wetsuit do I need?",
    "What breaks are like Snapper Rocks but quieter?",
]


def build_agent(selected, store, records: list[dict], vocab: dict | None,
                visible: bool = False) -> dict:
    """Build the agent bar (full width, hidden until agentic mode slides on)."""
    states = list((vocab or {}).get("states") or [])
    regions_by_state = dict((vocab or {}).get("regions_by_state") or {})
    all_regions = list((vocab or {}).get("all_regions") or [])

    with gr.Column(elem_classes=["agent-col"], visible=visible) as agent_col:
        gr.Markdown("### 💬 ask the agent — engines compute, the llm narrates")
        gr.Markdown("the agent calls ⚙ scoring, 🪨 the gebco world model, 🌡 era5 climate "
                    "and 📡 open-meteo directly; nemotron 3 ultra only narrates their "
                    "numbers. every answer lands with a question-matched chart — "
                    "recommended-scores leaderboard, week strip, rose, depth map, "
                    "similarity bars or component split.")
        ctx_md = gr.Markdown("", elem_classes=["ctx-line"])
        with gr.Row():
            with gr.Column(scale=1):
                with gr.Row(elem_classes=["agent-controls"]):
                    state_dd = gr.Dropdown([C.ALL, *states], value=C.ALL,
                                           label="State", min_width=120)
                    region_dd = gr.Dropdown([C.ALL, *all_regions], value=C.ALL,
                                            label="Region", min_width=120)
                    steps_slider = gr.Slider(1, 12, step=1,
                                             value=_DEFAULT_STEPS,
                                             label="max calls", scale=2,
                                             min_width=180,
                                             elem_classes=["steps-slider"])
                token_box = gr.Textbox(label="HF token (optional, session-only)", type="password",
                                       placeholder="Defaults to the Space secret — never logged or saved.")
                chatbot = gr.Chatbot(label="Surf agent", height=460)
                with gr.Row(elem_classes=["chat-input-row"]):
                    msg = gr.Textbox(show_label=False,
                                     placeholder="e.g. When should I surf Bells Beach this week? (Enter to send)",
                                     container=False, scale=8)
                    send_btn = gr.Button("Send", variant="primary", scale=1)
                    clear_btn = gr.Button("Clear", variant="stop", scale=1)
                trace_html = gr.HTML(_trace_html([]))
            with gr.Column(scale=1):
                verdict_html = gr.HTML("", elem_classes=["verdict-slot"])
                chips = [gr.Button(p, variant="secondary", elem_classes=["chip-btn"])
                         for p in CHIP_PROMPTS]
                token_md = gr.Markdown("_Token meter — per-turn usage lands here._")
                status_box = gr.Textbox(label="Status", interactive=False,
                                        placeholder="Ask anything — every answer lands with a chart…")
                spot_dd = gr.Dropdown(choices=[], value=None, visible=False, label="Chart spot (multiple scored)")
                agent_strip = gr.Plot(label="week strip — agent-scored spot")
                rank_html = gr.HTML(_EMPTY_RANK_HTML)

    def _chat(message, history, skill, hf_token, sel, st, steps, state, region):
        yield from chat_fn(message, history, skill, hf_token, sel, st,
                           steps, state, region, records)

    def agent_state_regions(state: str):
        """Page-one pattern: the State pick rewrites the Region choices."""
        regions = regions_by_state.get(state, all_regions) if state != C.ALL else all_regions
        return gr.update(choices=[C.ALL, *regions], value=C.ALL)

    def _show(label, st):
        return show_spot(label, st, records)

    def _chip(text):
        return lambda: text

    return {
        "agent_col": agent_col,
        "token_box": token_box, "chatbot": chatbot, "msg": msg,
        "send_btn": send_btn, "clear_btn": clear_btn, "trace_html": trace_html,
        "verdict_html": verdict_html, "rank_html": rank_html,
        "token_md": token_md, "agent_status": status_box, "spot_dd": spot_dd,
        "agent_strip": agent_strip, "chips": tuple(chips),
        "steps_slider": steps_slider, "state_dd": state_dd,
        "region_dd": region_dd, "ctx_md": ctx_md,
        "chat": _chat, "show_spot": _show, "clear": clear_chat, "chip_text": _chip,
        "ctx": ctx_line, "state_regions": agent_state_regions,
    }
