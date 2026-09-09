"""Agent panel: chat with tool cards, token meter, charts from tool payloads.

Consumes typed v2 agent events (``token | tool_call | tool_result | final |
usage``) from :func:`ui._compat.agent_run_stream`. Tool calls render as
cards in the activity box, per-turn prompt/completion tokens render in the
meter, and any ``score_week`` payload in a tool result is charted
immediately (the LLM never owns numbers).

The BYO HF token box is session-only: the value is passed straight to the
agent factory per turn, never stored, never logged.
"""

from __future__ import annotations

import json

import gradio as gr
import pandas as pd

from ui import _compat as C
from ui import _stubs as _stub
from ui.charts import score as score_chart
from ui.charts import swell as swell_chart
from ui.charts import wind as wind_chart

_SKILLS = _stub.SKILL_ORDER
_EMPTY_RANK = pd.DataFrame(columns=["Rank", "Spot", "Region", "Best score", "Best time"])


def _short_args(args: dict, limit: int = 160) -> str:
    try:
        text = json.dumps(args, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(args)
    return text if len(text) <= limit else text[: limit - 1] + "…"


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


def _format_rank_table(rank: list[dict] | None) -> pd.DataFrame:
    if not rank:
        return _EMPTY_RANK
    rows = [(i + 1, r.get("name", "?"), r.get("region", "?"),
             r.get("best_score", ""), r.get("best_time", ""))
            for i, r in enumerate(rank)]
    return pd.DataFrame(rows, columns=["Rank", "Spot", "Region", "Best score", "Best time"])


def _format_meter(usage: dict | None, source: str) -> str:
    if not usage:
        return f"_Token meter — per-turn usage lands here (via {source})._"
    if usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None:
        p = usage.get("prompt_tokens", "?")
        c = usage.get("completion_tokens", "?")
        try:
            total = int(p) + int(c)
        except (TypeError, ValueError):
            total = "?"
        return (f"🪙 **prompt {p} · completion {c} · total {total} tokens** "
                f"(this turn, via {source})")
    steps = usage.get("steps", "?")
    calls = usage.get("tool_calls") or {}
    n_calls = sum(calls.values()) if isinstance(calls, dict) else "?"
    model = str(usage.get("model") or "").split("/")[-1]
    return (f"⚙️ **{steps} steps · {n_calls} tool call(s)**"
            + (f" · {model}" if model else "")
            + f" (this turn, via {source})")


def fresh_store() -> dict:
    return {"spots": [], "rank": None, "usage": None}


def _build_trio(hours: list[dict], label: str, skill: str, records: list[dict]):
    spot_name = label.split(" (")[0]
    match = C.find_break(records, spot_name)
    spot = _scoring_spot(match)
    return (score_chart.build_score_fig(hours),
            swell_chart.build_waves_fig(hours),
            wind_chart.build_wind_fig(hours, spot),
            score_chart.format_best(score_chart.best_window(hours), label, skill))


def chat_fn(message: str, history: list[dict] | None, skill: str,
            hf_token: str, selected: dict | None, store: dict | None,
            records: list[dict]):
    """Stream an agent turn: tool cards + meter + charts + final answer."""
    history = list(history or [])
    store = dict(store or fresh_store())
    cards: list[str] = [f"ask: {(message or '').strip()[:140]}"]
    usage = None
    token_source = "session token" if (hf_token or "").strip() else "space secret / env"
    meter = _format_meter(None, token_source)
    spots = list(store.get("spots") or [])
    rank = store.get("rank")

    def emit(status, score_fig=None, swell_fig=None, wind_fig=None,
             spot_update=None, rank_df=None):
        return (history, "", "\n\n".join(cards), meter, status,
                score_fig if score_fig is not None else gr.skip(),
                swell_fig if swell_fig is not None else gr.skip(),
                wind_fig if wind_fig is not None else gr.skip(),
                spot_update if spot_update is not None else gr.skip(),
                rank_df if rank_df is not None else gr.skip(),
                dict(store, spots=spots, rank=rank, usage=usage))

    text = (message or "").strip()
    if not text:
        yield emit("⚠️ Type a question first.")
        return
    history = [*history, {"role": "user", "content": text}, {"role": "assistant", "content": ""}]
    yield emit("⏳ Agent thinking…")

    skill = (skill or "intermediate").strip().lower()
    try:
        stream = C.agent_run_stream(text, skill=skill, hf_token=hf_token or "",
                                    selected_break=selected)
        for kind, payload in stream:
            if kind == "token":
                history[-1]["content"] += str(payload)
                yield emit("💬 Streaming answer…")
            elif kind == "tool_call":
                d = payload if isinstance(payload, dict) else {"name": str(payload)}
                name = str(d.get("name", "?"))
                cards.append(f"🔧 `{name}({_short_args(d.get('arguments', {}))})`")
                yield emit(f"🔧 {name} — ⚙ scorer + 🌍 world model…")
            elif kind == "tool_result":
                d = payload if isinstance(payload, dict) else {}
                name = str(d.get("name", "?"))
                summary = d.get("summary") or "done"
                ms = d.get("ms")
                badge = f" · ⚡ {float(ms):.0f} ms" if isinstance(ms, (int, float)) else ""
                cards.append(f"📦 `{name}` → {summary}{badge}")
                obs = d.get("observation")
                hours = score_chart.coerce_scored_hours(obs)
                if hours:
                    args = d.get("arguments") or {}
                    spot_name = args.get("spot_name")
                    region = args.get("region")
                    if isinstance(obs, dict):
                        info = obs.get("spot") or {}
                        spot_name = spot_name or info.get("name")
                        region = region or info.get("region")
                    label = f"{spot_name} ({region})" if spot_name and region else (spot_name or f"spot {len(spots) + 1}")
                    entry_skill = skill
                    if isinstance(obs, dict) and obs.get("skill"):
                        entry_skill = obs["skill"]
                    spots.append({"label": label, "hours": hours, "skill": entry_skill})
                    seen: dict[str, int] = {}
                    for s in spots:
                        seen[s["label"]] = seen.get(s["label"], 0) + 1
                        if seen[s["label"]] > 1:
                            s["label"] = f"{s['label']} #{seen[s['label']]}"
                    s_fig, w_fig, wi_fig, best_md = _build_trio(hours, label, entry_skill, records)
                    history[-1]["content"] += f"\n\n📊 _Charted below: {label} — {best_md}_"
                    labels = [s["label"] for s in spots]
                    yield emit(f"📊 Charted '{label}' — agent still thinking…",
                               s_fig, w_fig, wi_fig,
                               gr.update(choices=labels, value=label, visible=len(labels) > 1))
                else:
                    rows = _coerce_rank_rows(obs)
                    if rows:
                        rank = rows
                        yield emit(f"🏆 Ranked {len(rows)} spot(s) — agent still thinking…",
                                   rank_df=_format_rank_table(rows))
                    else:
                        yield emit(f"📦 {name} done — agent still thinking…")
            elif kind == "usage":
                usage = payload if isinstance(payload, dict) else None
                meter = _format_meter(usage, token_source)
                yield emit("🪙 Usage recorded — agent still thinking…")
            elif kind == "final":
                history[-1]["content"] = str(payload) if payload else history[-1]["content"]
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

    labels = [s["label"] for s in spots]
    yield (history, "", "\n\n".join(cards), meter,
           "✅ Answer complete." if spots or rank else "💬 No scored forecast — ask for a specific break to see charts.",
           gr.skip(), gr.skip(), gr.skip(),
           gr.update(choices=labels, value=(labels[0] if labels else None),
                     visible=len(labels) > 1),
           _format_rank_table(rank),
           dict(store, spots=spots, rank=rank, usage=usage))


def show_spot(label: str | None, store: dict | None, records: list[dict]):
    """Rebuild agent-tab charts for the spot picked in the dropdown."""
    spots = (store or {}).get("spots") or []
    entry = next((s for s in spots if s.get("label") == label), None)
    if entry is None:
        return gr.skip(), gr.skip(), gr.skip()
    try:
        s_fig, w_fig, wi_fig, _ = _build_trio(entry["hours"], entry["label"],
                                              entry.get("skill", "intermediate"), records)
        return s_fig, w_fig, wi_fig
    except Exception:
        return gr.skip(), gr.skip(), gr.skip()


def clear_chat():
    """Reset the agent tab (session token box is a component, untouched)."""
    return ([], "", "", _format_meter(None, "space secret / env"), "Ask about a break — charts appear as spots are scored…",
            None, None, None, gr.update(choices=[], value=None, visible=False),
            _EMPTY_RANK, fresh_store())


def build_agent(selected, store, records: list[dict]) -> dict:
    """Build the agent tab. Returns component dict for wiring."""
    with gr.Tab("surf agent"):
        gr.Markdown("### surf agent")
        gr.Markdown("the agent calls the deterministic engines directly — ⚙ scoring, 🌍 GEBCO "
                    "world model, 📡 open-meteo feeds — and the LLM (Nemotron 3.5 Lightning) "
                    "only narrates their numbers. charts appear as spots are scored.")
        with gr.Row():
            skill_dd = gr.Dropdown(_SKILLS, value="intermediate", label="Skill level")
            token_box = gr.Textbox(label="HF token (optional, session-only)", type="password",
                                   placeholder="Defaults to the Space secret — never logged or saved.")
        with gr.Row():
            chip1 = gr.Button("Best in NSW this weekend (beginner)", variant="secondary")
            chip2 = gr.Button("Bells Beach mornings?", variant="secondary")
            chip3 = gr.Button("Quieter like Snapper?", variant="secondary")
        chatbot = gr.Chatbot(label="Surf agent", height=420)
        with gr.Row():
            msg = gr.Textbox(show_label=False, placeholder="e.g. When should I surf Bells Beach this week? (Enter to send)",
                             container=False, scale=8)
            send_btn = gr.Button("Send", variant="primary", scale=1)
            clear_btn = gr.Button("Clear", variant="stop", scale=1)
        telemetry_md = gr.Markdown("_Send a question — tool calls land here live._")
        token_md = gr.Markdown(_format_meter(None, "space secret / env"))
        status_box = gr.Textbox(label="Status", interactive=False,
                                placeholder="Ask about a break — charts appear as spots are scored…")
        spot_dd = gr.Dropdown(choices=[], value=None, visible=False, label="Chart spot (multiple scored)")
        with gr.Tabs():
            with gr.Tab("Score"):
                agent_score = gr.Plot(label="Score (0-10)")
            with gr.Tab("Swell"):
                agent_swell = gr.Plot(label="Swell")
            with gr.Tab("Wind"):
                agent_wind = gr.Plot(label="Wind (kt)")
        rank_df = gr.Dataframe(headers=["Rank", "Spot", "Region", "Best score", "Best time"],
                               label="Leaderboard", wrap=True)

    def _chat(message, history, skill, hf_token, sel, st):
        yield from chat_fn(message, history, skill, hf_token, sel, st, records)

    def _show(label, st):
        return show_spot(label, st, records)

    def _chip(text):
        return lambda: text

    return {
        "skill_dd": skill_dd, "token_box": token_box, "chatbot": chatbot, "msg": msg,
        "send_btn": send_btn, "clear_btn": clear_btn, "telemetry_md": telemetry_md,
        "token_md": token_md, "status_box": status_box, "spot_dd": spot_dd,
        "agent_score": agent_score, "agent_swell": agent_swell, "agent_wind": agent_wind,
        "rank_df": rank_df, "chips": (chip1, chip2, chip3), "chat": _chat,
        "show_spot": _show, "clear": clear_chat, "chip_text": _chip,
    }
