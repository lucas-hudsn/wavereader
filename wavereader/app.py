"""Gradio UI for wavereader: Australia map home, agent chat with trace panel,
interactive seaborn-styled plotly charts, weekly rankings, and the daggr
Morning Surf Report canvas.

Run with: uv run python -m wavereader.app
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading

import gradio as gr
import plotly.graph_objects as go

from wavereader import spots, tools
from wavereader.agent import PROVIDER_HF, PROVIDER_NIM, SurfAgent

# ---------------------------------------------------------------------------
# Styling: seaborn "muted" palette applied to plotly
# ---------------------------------------------------------------------------

MUTED = {
    "blue": "#4878D0",
    "orange": "#EE854A",
    "green": "#6ACC64",
    "red": "#D65F5F",
    "purple": "#B47CC7",
    "brown": "#8C613C",
    "pink": "#DC7EC0",
    "gray": "#797979",
    "gold": "#D5BB67",
    "cyan": "#82C6E2",
}

SKILL_COLORS = {
    "beginner": MUTED["green"],
    "intermediate": MUTED["cyan"],
    "advanced": MUTED["orange"],
    "expert": MUTED["red"],
}

REGIONS = ["NSW", "QLD", "VIC", "WA", "SA", "TAS"]
SKILL_FILTERS = ["all", "beginner", "intermediate", "advanced", "expert"]

_DEG_TO_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _compass(deg) -> str:
    if deg is None:
        return "–"
    try:
        deg = float(deg)
    except (TypeError, ValueError):
        return "–"
    return _DEG_TO_COMPASS[int((deg % 360) / 22.5) % 16]


def _primary_skill(skill_level: str) -> str:
    """Collapse compound skill strings ('beginner to intermediate') to a bucket."""
    s = (skill_level or "").lower()
    if "elite" in s or "professional" in s:
        return "expert"
    for level in ("beginner", "intermediate", "advanced", "expert"):
        if level in s:
            return level
    return "intermediate"


def _matches_skill(skill_level: str, wanted: str) -> bool:
    if wanted in (None, "", "all"):
        return True
    s = (skill_level or "").lower()
    if wanted == "expert":
        return "expert" in s or "elite" in s or "professional" in s
    return wanted in s


def create_seaborn_template() -> dict:
    """Plotly layout template with seaborn aesthetics (whitegrid + muted)."""
    return {
        "layout": {
            "font": {"family": "DejaVu Sans, Helvetica, Arial, sans-serif", "size": 13, "color": "#3b3b3b"},
            "paper_bgcolor": "white",
            "plot_bgcolor": "white",
            "colorway": list(MUTED.values()),
            "title": {"font": {"size": 17, "color": "#1f2d3d"}, "x": 0.01, "xanchor": "left"},
            "legend": {"bgcolor": "rgba(0,0,0,0)", "orientation": "h", "y": 1.08},
            "xaxis": {"gridcolor": "#e6e6e6", "zerolinecolor": "#e6e6e6", "linecolor": "#cccccc"},
            "yaxis": {"gridcolor": "#e6e6e6", "zerolinecolor": "#e6e6e6", "linecolor": "#cccccc"},
            "margin": {"l": 60, "r": 70, "t": 70, "b": 55},
        }
    }


def _style(fig: go.Figure) -> go.Figure:
    fig.update_layout(**create_seaborn_template()["layout"])
    return fig


def _empty_fig(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=15, color="#888888"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _style(fig)


# ---------------------------------------------------------------------------
# Charts (plotly, seaborn-styled)
# ---------------------------------------------------------------------------

def create_australia_map(skill_filter: str = "all") -> go.Figure:
    """Scattergeo of all knowledge-base breaks, coloured by skill bucket."""
    lats, lngs, names, texts, colors, labels = [], [], [], [], [], []
    for b in spots.load_breaks():
        if not _matches_skill(b.additional_details.skill_level, skill_filter):
            continue
        swell = b.ideal_swell
        wind = b.ideal_wind
        lats.append(b.coordinates.lat)
        lngs.append(b.coordinates.lng)
        names.append(b.name)
        labels.append(f"{b.name} ({b.region})")
        colors.append(SKILL_COLORS.get(_primary_skill(b.additional_details.skill_level), MUTED["gray"]))
        texts.append(
            f"<b>{b.name}</b> ({b.region})<br>"
            f"Skill: {b.additional_details.skill_level}<br>"
            f"Ideal swell: {swell.size_ft_min}–{swell.size_ft_max} ft {swell.direction}<br>"
            f"Ideal wind: ≤{wind.strength_kt_max} kt {wind.direction}"
        )

    fig = go.Figure(
        go.Scattergeo(
            lat=lats,
            lon=lngs,
            text=names,
            customdata=labels,
            hovertext=texts,
            hoverinfo="text",
            mode="markers",
            marker=dict(size=9, color=colors, opacity=0.85, line=dict(width=1, color="white")),
            showlegend=False,
        )
    )
    fig.update_layout(
        title=dict(text="Australian Surf Breaks", font=dict(size=17, color="#1f2d3d")),
        geo=dict(
            scope="world",
            projection=dict(type="mercator"),
            center=dict(lat=-25.5, lon=134.5),
            lonaxis_range=[111, 156],
            lataxis_range=[-44, -9.5],
            showland=True,
            landcolor="#f3efe4",
            showocean=True,
            oceancolor="#d7e9f5",
            showcountries=False,
            showcoastlines=True,
            coastlinecolor="#9bb8cc",
            showlakes=False,
            bgcolor="#d7e9f5",
        ),
        height=560,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        font={"family": "DejaVu Sans, Helvetica, Arial, sans-serif", "size": 13, "color": "#3b3b3b"},
    )
    return fig


def create_wave_height_chart(forecast: dict, spot_name: str) -> go.Figure:
    """Hourly wave height (left axis) + period and wind speed (right axis)."""
    hourly = (forecast or {}).get("hourly") or []
    if not hourly:
        return _empty_fig(f"No forecast data available for {spot_name}")

    times = [h.get("time", "") for h in hourly]
    wave = [h.get("wave_height") for h in hourly]
    period = [h.get("wave_period") for h in hourly]
    wind = [h.get("wind_speed_10m") for h in hourly]
    wind_dir = [h.get("wind_direction_10m") for h in hourly]
    wave_dir = [h.get("wave_direction") or h.get("swell_wave_direction") for h in hourly]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times, y=wave, name="Wave height (m)", mode="lines",
            line=dict(color=MUTED["blue"], width=3), fill="tozeroy",
            fillcolor="rgba(72,120,208,0.12)",
            customdata=list(zip([_compass(d) for d in wave_dir], [d for d in wave_dir])),
            hovertemplate="%{x}<br>Wave height: %{y:.2f} m<br>Swell dir: %{customdata[0]} (%{customdata[1]}°)<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times, y=period, name="Period (s)", mode="lines",
            line=dict(color=MUTED["purple"], width=2, dash="dot"),
            yaxis="y2",
            hovertemplate="%{x}<br>Period: %{y:.1f} s<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=times, y=wind, name="Wind (km/h)", mode="lines",
            line=dict(color=MUTED["red"], width=2),
            yaxis="y2",
            customdata=[_compass(d) for d in wind_dir],
            hovertemplate="%{x}<br>Wind: %{y:.1f} km/h %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Wave & Wind Forecast — {spot_name}",
        xaxis=dict(title="Time (local)"),
        yaxis=dict(title="Wave height (m)", rangemode="tozero"),
        yaxis2=dict(title="Period (s) / Wind (km/h)", overlaying="y", side="right", showgrid=False),
        hovermode="x unified",
    )
    return _style(fig)


def create_score_chart(scores: list, spot_name: str) -> go.Figure:
    """Hourly surf score (bold) with the four deterministic components."""
    if not scores:
        return _empty_fig(f"No score data available for {spot_name}")

    times = [s.get("time", "") for s in scores]
    total = [s.get("score") for s in scores]
    comps = scores[0].get("components") or {}

    fig = go.Figure()
    component_colors = {
        "swell_size": MUTED["blue"],
        "swell_direction": MUTED["cyan"],
        "wind": MUTED["red"],
        "period": MUTED["purple"],
    }
    for comp in ("swell_size", "swell_direction", "wind", "period"):
        if comp in comps:
            fig.add_trace(
                go.Scatter(
                    x=times,
                    y=[(s.get("components") or {}).get(comp) for s in scores],
                    name=comp.replace("_", " ").title(),
                    mode="lines",
                    line=dict(color=component_colors[comp], width=1.5, dash="dot"),
                    opacity=0.75,
                    hovertemplate="%{x}<br>" + comp.replace("_", " ") + ": %{y:.1f}<extra></extra>",
                )
            )
    fig.add_trace(
        go.Scatter(
            x=times, y=total, name="Surf score", mode="lines",
            line=dict(color="#1f2d3d", width=3.5),
            hovertemplate="%{x}<br>Score: %{y:.1f}/10<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Hourly Surf Score — {spot_name}",
        xaxis=dict(title="Time (local)"),
        yaxis=dict(title="Score (0–10)", range=[0, 10]),
        hovermode="x unified",
    )
    return _style(fig)


def create_ranking_chart(ranked: list, region: str) -> go.Figure:
    """Horizontal bars of each spot's best score this week."""
    if not ranked:
        return _empty_fig(f"No ranking data for {region}")
    spots_sorted = sorted(ranked, key=lambda r: r.get("best_score") or 0)
    names = [f"{r.get('name', '?')} ({r.get('region', '')})" for r in spots_sorted]
    values = [r.get("best_score") or 0 for r in spots_sorted]
    best_times = [r.get("best_time", "–") for r in spots_sorted]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker=dict(
                color=values,
                colorscale=[[0, MUTED["cyan"]], [0.6, MUTED["blue"]], [1, MUTED["green"]]],
                line=dict(width=0),
            ),
            customdata=best_times,
            hovertemplate="%{y}<br>Best score: %{x:.1f}/10<br>Best time: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        title=f"Best Scores This Week — {region}",
        xaxis=dict(title="Best hourly score (0–10)", range=[0, 10]),
        yaxis=dict(title=""),
        height=max(360, 28 * len(names) + 120),
    )
    return _style(fig)


# ---------------------------------------------------------------------------
# Trace panel
# ---------------------------------------------------------------------------

_TOOL_EMOJI = {
    "get_forecast": "🌊",
    "score_week": "🧮",
    "find_spots": "🔎",
    "get_spot_knowledge": "📚",
    "rank_spots_this_week": "🏆",
}

# Tool invocations inside CodeAgent python_interpreter code blobs
_TOOL_CALL_RE = re.compile(
    r"\b(get_forecast|score_week|find_spots|get_spot_knowledge|rank_spots_this_week)\(([^)]*)"
)


def _code_step_summary(args) -> tuple[str, list[tuple[str, str]]]:
    """Summarise a python_interpreter code blob: (display_code, tool calls)."""
    code = args if isinstance(args, str) else str(args)
    calls = [
        (tool, re.findall(r"[\"']([^\"']+)[\"']", argstr))
        for tool, argstr in _TOOL_CALL_RE.findall(code)
    ]
    snippet = code.strip().replace("```", "")
    if len(snippet) > 400:
        snippet = snippet[:400] + " …"
    return snippet, calls


def update_trace_panel(trace_json: str) -> str:
    """Render an AgentTrace JSON blob as readable markdown for the UI."""
    if not trace_json or not trace_json.strip():
        return (
            "### 🔍 Agent Trace\n\nNo trace yet — ask the agent a question and "
            "watch it work: every tool call, the data it saw, and its reasoning "
            "appear here."
        )
    try:
        trace = json.loads(trace_json)
    except (json.JSONDecodeError, TypeError):
        return trace_json

    lines = ["### 🔍 Agent Trace"]
    question = trace.get("question", "")
    if question:
        lines.append(f"**Question:** {question}")
    model = trace.get("model", "")
    provider = trace.get("provider", "")
    if model or provider:
        lines.append(f"**Model:** `{model}` via `{provider}`")
    lines.append("")

    n_chunks = 0
    for evt in trace.get("events", []):
        etype = evt.get("type", "")
        data = evt.get("data", {})
        if etype == "tool_call":
            name = data.get("name", "?")
            args = data.get("arguments", {})
            if name == "python_interpreter":
                snippet, calls = _code_step_summary(args)
                called = ", ".join(f"`{tool}`" for tool, _ in calls) if calls else ""
                lines.append(f"- 🧠 **code step** {f'→ calls {called}' if called else ''}")
                lines.append(f"\n```python\n{snippet}\n```\n")
            else:
                emoji = _TOOL_EMOJI.get(name, "🔧")
                if isinstance(args, str):
                    args_display = args
                else:
                    args_display = ", ".join(
                        f"{k}=`{v}`" for k, v in args.items() if v is not None
                    )
                lines.append(f"- {emoji} **`{name}`**({args_display})")
        elif etype == "tool_result":
            obs = str(data.get("observation", ""))
            if len(obs) > 220:
                obs = obs[:220] + "…"
            lines.append(f"  - ↳ *{obs}*")
        elif etype == "llm_chunk":
            n_chunks += 1
        elif etype == "final_answer":
            lines.append("- ✅ **Final answer** composed")
    if n_chunks:
        lines.append(f"- 💬 Streamed {n_chunks} token chunks")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data helpers for the UI
# ---------------------------------------------------------------------------

def _spot_label(b) -> str:
    return f"{b.name} ({b.region})"


def _all_spot_choices() -> list[str]:
    return sorted(_spot_label(b) for b in spots.load_breaks())


def _parse_spot_label(label: str):
    m = re.match(r"^(.*) \(([A-Z]{2,3})\)$", label or "")
    if not m:
        return None
    return spots.get_spot(m.group(1), m.group(2))


def _spot_card(spot) -> str:
    if spot is None:
        return "_Select a break to see its profile._"

    def badge(text: str, color: str) -> str:
        return (
            f"<span class='skill-badge' style='background:{color}22; color:{color}; "
            f"border:1px solid {color}66'>{text}</span>"
        )

    d = spot.additional_details
    swell = spot.ideal_swell
    wind = spot.ideal_wind
    badges = " ".join(
        badge(t, SKILL_COLORS.get(_primary_skill(t), MUTED["gray"]))
        for t in (d.skill_level, d.break_type, d.break_direction)
    )
    hazards = d.hazards or "—"
    return f"""
### 🏄 {spot.name} · {spot.region}

{badges}

{spot.short_description}

| Ideal conditions | |
|---|---|
| **Swell** | {swell.size_ft_min}–{swell.size_ft_max} ft from {swell.direction} |
| **Wind** | offshore/low up to {wind.strength_kt_max} kt ({wind.direction}) |
| **Tide** | {spot.ideal_tide} *(qualitative)* |
| **Bottom** | {d.bottom_type} · {d.break_surface} |
| **Best season** | {d.best_season} |

⚠️ **Hazards:** {hazards}

{d.other_notes or ""}
"""


def _get_spot_data(spot):
    """Forecast + scores for a spot, with a small in-process cache."""
    if spot is None:
        return None, None
    cache = getattr(_get_spot_data, "_cache", None)
    if cache is None:
        cache = _get_spot_data._cache = {}
    key = (spot.name, spot.region)
    if key not in cache:
        forecast = tools.get_forecast(spot.name, spot.region)
        if "error" in forecast:
            return None, None
        scores = tools.score_week(spot.name, spot.region)
        if isinstance(scores, dict) and "error" in scores:
            scores = []
        cache[key] = (forecast, scores)
    return cache[key]


def _guess_region(name: str) -> str | None:
    """Resolve a spot's region from the knowledge base by exact name."""
    for b in spots.load_breaks():
        if b.name.lower() == name.lower():
            return b.region
    return None


def _extract_trace_targets(trace_json: str) -> tuple[list[tuple[str, str | None]], list[str]]:
    """What the agent looked at, from python_interpreter code blobs.

    Returns (spot_pairs, rank_regions): spot (name, region-or-None) pairs for
    forecast/score/knowledge calls, and regions passed to ranking calls.
    """
    spot_pairs: list[tuple[str, str | None]] = []
    rank_regions: list[str] = []
    try:
        trace = json.loads(trace_json)
    except (json.JSONDecodeError, TypeError):
        return spot_pairs, rank_regions
    for evt in trace.get("events", []):
        if evt.get("type") != "tool_call":
            continue
        args = evt.get("data", {}).get("arguments")
        code = args if isinstance(args, str) else json.dumps(args or {})
        for tool, vals in (
            (t, re.findall(r"[\"']([^\"']+)[\"']", a))
            for t, a in _TOOL_CALL_RE.findall(code)
        ):
            if tool in ("get_forecast", "score_week") and len(vals) >= 2:
                pair = (vals[0], vals[1])
            elif tool == "get_spot_knowledge" and vals:
                pair = (vals[0], vals[1] if len(vals) >= 2 else None)
            elif tool == "rank_spots_this_week" and vals:
                if vals[0] not in rank_regions:
                    rank_regions.append(vals[0])
                continue
            else:
                continue
            if pair not in spot_pairs:
                spot_pairs.append(pair)
    return spot_pairs, rank_regions


# ---------------------------------------------------------------------------
# Agent chat
# ---------------------------------------------------------------------------

_agents: dict[str, SurfAgent] = {}


def _get_agent(provider: str) -> SurfAgent:
    if provider not in _agents:
        _agents[provider] = SurfAgent(provider=provider)
    return _agents[provider]


def _provider_available(provider: str) -> bool:
    if provider == PROVIDER_NIM:
        return bool(os.getenv("NVIDIA_API_KEY"))
    return bool(os.getenv("HF_TOKEN"))


def chat_submit(message: str, history: list, provider: str):
    """Streaming chat handler: yields (chatbot, trace_md, score_chart, wave_chart)."""
    history = list(history or [])
    if not message or not message.strip():
        yield history, gr.update(), gr.update(), gr.update()
        return

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": "…"})

    try:
        agent = _get_agent(provider)
    except ValueError as exc:
        history[-1]["content"] = (
            f"⚠️ **Model provider not configured.**\n\n{exc}\n\n"
            "Set `HF_TOKEN` or `NVIDIA_API_KEY` in your environment and restart. "
            "Everything else (map, charts, rankings, scores) works without tokens."
        )
        yield history, gr.update(), gr.update(), gr.update()
        return

    thinking: list[str] = []
    final_answer = ""
    trace_json = ""
    for kind, chunk in agent.run_stream(message):
        if kind == "model":
            thinking.append(chunk)
            tail = "".join(thinking)[-600:]
            history[-1]["content"] = f"*🧠 thinking…*\n\n```python\n{tail}\n```"
            yield history, gr.update(), gr.update(), gr.update()
        elif kind == "tool":
            history[-1]["content"] = f"*🔧 calling `{chunk}`…*"
            yield history, gr.update(), gr.update(), gr.update()
        elif kind == "final":
            final_answer = chunk if isinstance(chunk, str) else str(chunk)
            trace_json = agent.trace.to_json() if agent.trace else ""

    history[-1]["content"] = final_answer or "*(empty answer)*"
    trace_md = update_trace_panel(trace_json)

    # Auto-render interactive charts for what the agent looked at
    score_fig: object = gr.update()
    wave_fig: object = gr.update()
    spot_pairs, rank_regions = _extract_trace_targets(trace_json)
    if spot_pairs:
        name, region = spot_pairs[0]
        region = region or _guess_region(name)
        spot = spots.get_spot(name, region) if region else None
        if spot is not None:
            forecast, scores = _get_spot_data(spot)
            if scores:
                score_fig = create_score_chart(scores[-48:], spot.name)
            if forecast:
                wave_fig = create_wave_height_chart(
                    {"hourly": forecast["hourly"][-48:]}, spot.name
                )
    elif rank_regions:
        ranked = tools.rank_spots_this_week(rank_regions[0], None)
        score_fig = create_ranking_chart(ranked, rank_regions[0])

    yield history, trace_md, score_fig, wave_fig


# ---------------------------------------------------------------------------
# daggr Morning Surf Report + cache warming (started only by main())
# ---------------------------------------------------------------------------

def _start_daggr_server(host: str = "127.0.0.1", port: int = 7861) -> None:
    """Launch the Morning Surf Report canvas as its own process.

    A second Gradio instance inside this process is unreliable, so the daggr
    app runs standalone; the tab's iframe just points at it.
    """
    try:
        subprocess.Popen(
            [sys.executable, "-m", "wavereader.daggr_pipeline"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass  # canvas tab falls back to a "how to start" note


def _warm_forecast_cache() -> None:
    """Prefetch all break forecasts into the disk cache (demo survivability)."""
    for b in spots.load_breaks():
        try:
            tools.get_forecast(b.name, b.region)
        except Exception:
            continue


def _start_background_services() -> None:
    if os.getenv("WAVEREADER_EMBED_DAGGR", "1") == "1":
        threading.Thread(target=_start_daggr_server, daemon=True).start()
    if os.getenv("WAVEREADER_WARM_CACHE", "1") == "1":
        threading.Thread(target=_warm_forecast_cache, daemon=True).start()


# ---------------------------------------------------------------------------
# UI assembly
# ---------------------------------------------------------------------------

_CUSTOM_CSS = """
.gradio-container {max-width: 1400px !important; margin: 0 auto;}
#wr-header {
    background: linear-gradient(120deg, #0b3d5c 0%, #1173a6 55%, #19b3a6 100%);
    border-radius: 16px; padding: 26px 30px !important; color: white;
    margin-bottom: 14px;
}
#wr-header h1 {color: white; margin: 0 0 6px 0; font-size: 2em; letter-spacing: 0.5px;}
#wr-header p {color: #d7ecf7; margin: 0; font-size: 1.02em;}
.skill-badge {
    display: inline-block; padding: 2px 10px; border-radius: 999px;
    font-size: 0.8em; font-weight: 600; white-space: nowrap;
}
#wr-trace {
    background: #f7fafc; border: 1px solid #e2e8f0; border-radius: 12px;
    padding: 10px 14px; font-size: 0.92em; max-height: 640px; overflow-y: auto;
}
#wr-trace code {background: #eef2f7; padding: 1px 5px; border-radius: 5px;}
footer {display: none !important;}
"""


def build_ui() -> gr.Blocks:
    """Assemble the full wavereader demo UI."""
    spot_choices = _all_spot_choices()
    hf_ok, nim_ok = _provider_available(PROVIDER_HF), _provider_available(PROVIDER_NIM)

    with gr.Blocks(
        title="WaveReader — Agentic Surf Forecaster",
        theme=gr.themes.Soft(
            primary_hue="sky",
            secondary_hue="blue",
            neutral_hue="slate",
            font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui"],
        ),
        css=_CUSTOM_CSS,
    ) as demo:

        # ------------------------------------------------ header
        status = "🟢 agent ready" if (hf_ok or nim_ok) else "🔴 set HF_TOKEN or NVIDIA_API_KEY for the agent"
        gr.HTML(
            f"""<div id="wr-header">
<h1>🏄 WaveReader</h1>
<p>Agentic surf forecaster for Australian breaks — deterministic scores, visible reasoning.
&nbsp;·&nbsp; Model: <code>Qwen/Qwen3-Next-80B-A3B-Instruct</code> &nbsp;·&nbsp; {status}</p>
</div>"""
        )

        with gr.Tabs():

            # ------------------------------------------------ tab: explore (map home)
            with gr.Tab("🗺️ Explore"):
                with gr.Row():
                    with gr.Column(scale=3):
                        map_plot = gr.Plot(create_australia_map(), label="Surf breaks across Australia", show_label=False)
                        map_skill_filter = gr.Dropdown(
                            choices=SKILL_FILTERS, value="all", label="Filter map by skill"
                        )
                    with gr.Column(scale=2):
                        gr.Markdown("### Pick your break")
                        spot_dropdown = gr.Dropdown(
                            choices=spot_choices,
                            value=None,
                            label="Search 100 breaks (name or region)",
                            info="Type to filter — e.g. 'Snapper' or 'QLD'",
                        )
                        spot_card_md = gr.Markdown(_spot_card(None))
                        spot_quick_btn = gr.Button(
                            "📊 Show forecast charts for this spot", variant="secondary"
                        )

            # ------------------------------------------------ tab: agent chat
            with gr.Tab("🤖 Surf Agent"):
                with gr.Row():
                    with gr.Column(scale=5):
                        provider_radio = gr.Radio(
                            choices=[
                                ("Hugging Face 🤗 (Qwen 80B)", PROVIDER_HF),
                                ("NVIDIA NIM ⚡ (Llama 3.2 90B)", PROVIDER_NIM),
                            ],
                            value=PROVIDER_HF if hf_ok else PROVIDER_NIM,
                            label="Model hosting",
                        )
                        chatbot = gr.Chatbot(
                            height=500,
                            label="WaveReader agent",
                            placeholder="Ask: *Where should I surf near Byron Bay this weekend as an intermediate?*",
                        )
                        with gr.Row():
                            chat_input = gr.Textbox(
                                placeholder="Ask about any break, your skill level, best hours…",
                                scale=8,
                                show_label=False,
                                autofocus=True,
                            )
                            chat_send = gr.Button("Send 🚀", variant="primary", scale=1)
                        gr.Examples(
                            examples=[
                                "Which QLD spots suit a beginner this week?",
                                "What time should I surf Snapper Rocks tomorrow?",
                                "Rank NSW breaks for an advanced surfer and explain the top pick.",
                            ],
                            inputs=[chat_input],
                        )
                    with gr.Column(scale=3):
                        trace_panel = gr.Markdown(update_trace_panel(""), elem_id="wr-trace")
                gr.Markdown("### Charts the agent surfaced")
                with gr.Row():
                    chat_score_chart = gr.Plot(
                        _empty_fig("Ask about a spot — its score chart appears here"),
                        label="Hourly surf score",
                    )
                    chat_wave_chart = gr.Plot(
                        _empty_fig("Ask about a spot — its forecast chart appears here"),
                        label="Wave & wind forecast",
                    )

            # ------------------------------------------------ tab: charts
            with gr.Tab("📊 Forecast Charts"):
                with gr.Row():
                    chart_spot = gr.Dropdown(choices=spot_choices, value=None, label="Spot")
                    chart_load_btn = gr.Button("Load charts", variant="primary")
                with gr.Row():
                    chart_wave_plot = gr.Plot(label="Wave height · period · wind")
                with gr.Row():
                    chart_score_plot = gr.Plot(label="Hourly surf score + components")

            # ------------------------------------------------ tab: rankings
            with gr.Tab("🏆 Weekly Rankings"):
                with gr.Row():
                    rank_region = gr.Dropdown(choices=REGIONS, value="NSW", label="Region")
                    rank_skill = gr.Dropdown(choices=SKILL_FILTERS, value="all", label="Skill level")
                    rank_btn = gr.Button("Rank this week", variant="primary")
                rank_plot = gr.Plot(label="Best scores this week")
                rank_table = gr.Dataframe(
                    headers=["Spot", "Region", "Best score", "Best time"],
                    label="Ranked table",
                    interactive=False,
                )

            # ------------------------------------------------ tab: morning report
            with gr.Tab("📋 Morning Surf Report"):
                gr.Markdown(
                    "The fixed **Morning Surf Report** pipeline (daggr): pick a region + "
                    "skill → find spots → fetch forecasts → score → rank → narrated report "
                    "with deterministic scores."
                )
                gr.HTML(
                    """<div style="border-radius:12px; border:1px solid #e2e8f0; overflow:hidden;">
<iframe src="http://127.0.0.1:7861" style="width:100%; height:760px; border:0;"></iframe>
</div>
<p><i>If the canvas is empty, start the pipeline app:
<code>uv run python -m wavereader.daggr_pipeline</code> (it runs alongside this UI on port 7861).</i></p>"""
                )

        # ------------------------------------------------ events: explore
        map_skill_filter.change(
            lambda skill: create_australia_map(skill),
            inputs=[map_skill_filter],
            outputs=[map_plot],
        )

        def show_spot_card(label):
            return _spot_card(_parse_spot_label(label))

        spot_dropdown.change(show_spot_card, inputs=[spot_dropdown], outputs=[spot_card_md])

        def jump_to_charts(label):
            spot = _parse_spot_label(label)
            if spot is None:
                return gr.update(), gr.update(), gr.update()
            forecast, scores = _get_spot_data(spot)
            wave = create_wave_height_chart(forecast, spot.name) if forecast else gr.update()
            score = create_score_chart(scores, spot.name) if scores else gr.update()
            return wave, score, gr.update(value=label)

        spot_quick_btn.click(
            jump_to_charts,
            inputs=[spot_dropdown],
            outputs=[chart_wave_plot, chart_score_plot, chart_spot],
        )

        # ------------------------------------------------ events: chat
        chat_send.click(
            chat_submit,
            inputs=[chat_input, chatbot, provider_radio],
            outputs=[chatbot, trace_panel, chat_score_chart, chat_wave_chart],
        )
        chat_input.submit(
            chat_submit,
            inputs=[chat_input, chatbot, provider_radio],
            outputs=[chatbot, trace_panel, chat_score_chart, chat_wave_chart],
        )

        # ------------------------------------------------ events: charts tab
        def load_charts(label):
            spot = _parse_spot_label(label)
            if spot is None:
                return _empty_fig("Pick a spot above"), _empty_fig("Pick a spot above")
            forecast, scores = _get_spot_data(spot)
            wave = create_wave_height_chart(forecast, spot.name) if forecast else _empty_fig("No forecast")
            score = create_score_chart(scores, spot.name) if scores else _empty_fig("No scores")
            return wave, score

        chart_load_btn.click(load_charts, inputs=[chart_spot], outputs=[chart_wave_plot, chart_score_plot])
        chart_spot.change(load_charts, inputs=[chart_spot], outputs=[chart_wave_plot, chart_score_plot])

        # ------------------------------------------------ events: rankings
        def run_ranking(region, skill):
            skill_arg = None if skill == "all" else skill
            ranked = tools.rank_spots_this_week(region, skill_arg)
            fig = create_ranking_chart(ranked, region)
            table = [
                [r.get("name"), r.get("region"), round(r.get("best_score") or 0, 1), r.get("best_time")]
                for r in ranked
            ]
            return fig, table

        rank_btn.click(run_ranking, inputs=[rank_region, rank_skill], outputs=[rank_plot, rank_table])

    return demo


def main() -> None:
    _start_background_services()
    demo = build_ui()
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
