"""Gradio map front end for Australian surf breaks."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

import gradio as gr
import pandas as pd
from plotly import graph_objects as go

DATA_PATH = Path(__file__).parent / "data" / "australia-surf-breaks-enriched.json"
GENERATOR_PATH = Path(__file__).parent / "app" / "generate_surf_break.py"
FORECAST_PATH = Path(__file__).parent / "app" / "surf_forecast.py"
REPORT_PATH = Path(__file__).parent / "app" / "generate_surf_report.py"
AGENT_PATH = Path(__file__).parent / "app" / "agent.py"
FAVICON_PATH = Path(__file__).parent / "assets" / "wave.svg"

ALL = "All"

SKILL_ORDER = ["beginner", "intermediate", "advanced", "expert", "pro-only"]
SKILL_COLORS = {
    "beginner": "#2ca02c",
    "intermediate": "#1f77b4",
    "advanced": "#ff7f0e",
    "expert": "#d62728",
    "pro-only": "#9467bd",
}
CUSTOM_MARKER_COLOR = "#FFD700"  # gold highlight for the session-only break
APP_CSS = """
/* wave~reader lo-fi theme: light blue bg (#eef6fd everywhere), dark blue font */
.gradio-container, .gradio-container-4x, main, body {
    background: #eef6fd !important;
    color: #0b2c5c !important;
    font-family: "Courier New", Courier, monospace !important;
}
.gradio-container h1, .gradio-container h2, .gradio-container h3,
.gradio-container p, .gradio-container span, .gradio-container label,
.gradio-container .markdown, .prose {
    color: #0b2c5c !important;
    font-family: "Courier New", Courier, monospace !important;
}
.hero-title {
    font-size: 2.2em !important;
    letter-spacing: 1px;
    text-transform: lowercase;
    margin-bottom: 0 !important;
}
button, select {
    font-family: "Courier New", Courier, monospace !important;
}
/* primary (orange) buttons -> dark blue */
.gradio-container {
    --button-primary-background-fill: #0b2c5c !important;
    --button-primary-background-fill-hover: #13407e !important;
    --button-primary-text-color: #ffffff !important;
    --button-primary-border-color: #0b2c5c !important;
}
.gradio-container button.primary,
.gradio-container .gr-button-primary,
button.primary, button.lg.primary {
    background: #0b2c5c !important;
    border-color: #0b2c5c !important;
    color: #ffffff !important;
}
.gradio-container button.primary:hover,
.gradio-container .gr-button-primary:hover,
button.primary:hover, button.lg.primary:hover {
    background: #13407e !important;
    border-color: #13407e !important;
    color: #ffffff !important;
}
.break-list { max-height: 210px; overflow-y: auto; border: 1px solid #0b2c5c; border-radius: 8px; padding: 4px; background: #eef6fd !important; }
/* selected break dot -> dark blue (radio circle fill + border) */
.break-list input[type="radio"]:checked,
.break-list input[type="checkbox"]:checked {
    background-color: #0b2c5c !important;
    border-color: #0b2c5c !important;
    accent-color: #0b2c5c !important;
}
.break-list label.selected {
    background: #d6e9f8 !important;
    color: #0b2c5c !important;
}
/* blocks match the page bg (#eef6fd) — padding + dark borders define them */
.gradio-container {
    --background-fill-primary: #eef6fd !important;
    --background-fill-secondary: #eef6fd !important;
    --block-background-fill: #eef6fd !important;
    --block-border-color: #0b2c5c !important;
    --block-label-background-fill: #eef6fd !important;
    --block-label-text-color: #0b2c5c !important;
    --input-background-fill: #ffffff !important;
    --input-border-color: #0b2c5c !important;
    --input-placeholder-color: #4a6fa5 !important;
    --table-background-fill: #eef6fd !important;
    --table-border-color: #0b2c5c !important;
    --table-odd-background-fill: #eef6fd !important;
    --table-even-background-fill: #eef6fd !important;
    --chatbot-code-background-fill: #eef6fd !important;
    --button-secondary-background-fill: #eef6fd !important;
    --button-secondary-background-fill-hover: #d6e9f8 !important;
    --button-secondary-text-color: #0b2c5c !important;
    --button-secondary-border-color: #0b2c5c !important;
    --button-cancel-background-fill: #eef6fd !important;
    --button-cancel-text-color: #0b2c5c !important;
    --button-cancel-border-color: #0b2c5c !important;
    --block-border-width: 2px !important;
    --block-shadow: none !important;
    --block-title-text-size: 15px !important;
    --checkbox-background-color-selected: #0b2c5c !important;
    --checkbox-border-color-selected: #0b2c5c !important;
    --checkbox-border-color-focus: #0b2c5c !important;
    --checkbox-border-color-hover: #0b2c5c !important;
    --checkbox-label-background-fill-selected: #d6e9f8 !important;
    --checkbox-label-text-color-selected: #0b2c5c !important;
}
.gradio-container .gr-box, .gradio-container .gr-panel,
.gradio-container .block, .gradio-container .form,
.gradio-container .gr-group, .gradio-container .gr-block,
.gradio-container .tabitem, .gradio-container .tabs {
    background: #eef6fd !important;
    border-color: #0b2c5c !important;
    border-width: 2px !important;
    border-radius: 12px !important;
    padding: 11px !important;
    gap: 8px !important;
}
.gradio-container input, .gradio-container textarea,
.gradio-container select, .gradio-container .gr-textbox,
.gradio-container .gr-dropdown, .gradio-container .gr-radio,
.gradio-container .gr-checkbox, .gradio-container .gr-dataframe {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
.gradio-container table, .gradio-container thead,
.gradio-container tbody, .gradio-container th,
.gradio-container td, .gradio-container .table-wrap {
    background: #eef6fd !important;
    color: #0b2c5c !important;
}
.gradio-container tbody tr:nth-child(even) {
    background: #eef6fd !important;
}
.gradio-container .message, .gradio-container .bubble,
.gradio-container .message-wrap {
    background: #ffffff !important;
    border-color: #0b2c5c !important;
    color: #0b2c5c !important;
}
/* browse tabs stand out: big lowercase pill tabs, same courier + dark blue */
.gradio-container .tab-nav {
    gap: 14px !important;
    padding: 6px 2px 12px 2px !important;
    border-bottom: 2px solid #0b2c5c !important;
    background: transparent !important;
}
.gradio-container .tab-nav button {
    background: #eef6fd !important;
    color: #0b2c5c !important;
    border: 2px solid #0b2c5c !important;
    border-radius: 999px !important;
    font-size: 1.15em !important;
    font-weight: bold !important;
    text-transform: lowercase !important;
    letter-spacing: 1px !important;
    padding: 10px 28px !important;
}
.gradio-container .tab-nav button:hover {
    background: #d6e9f8 !important;
}
.gradio-container .tab-nav button.selected {
    background: #0b2c5c !important;
    color: #ffffff !important;
    border-color: #0b2c5c !important;
}
/* agentic-mode sliding toggle: style the checkbox as an on/off switch */
.mode-switch input[type="checkbox"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 52px !important;
    height: 28px !important;
    border-radius: 999px !important;
    background: #8fb8dd !important;
    border: 2px solid #0b2c5c !important;
    position: relative !important;
    cursor: pointer !important;
    outline: none !important;
    flex-shrink: 0 !important;
}
.mode-switch input[type="checkbox"]::after {
    content: "" !important;
    position: absolute !important;
    top: 1px !important;
    left: 2px !important;
    width: 20px !important;
    height: 20px !important;
    border-radius: 50% !important;
    background: #ffffff !important;
    border: 2px solid #0b2c5c !important;
    transition: left 0.15s ease-in-out !important;
}
.mode-switch input[type="checkbox"]:checked {
    background: #0b2c5c !important;
}
.mode-switch input[type="checkbox"]:checked::after {
    left: 24px !important;
}
/* header row: title left, compact toggle pinned top-right */
.header-row { align-items: flex-start !important; }
/* messenger-style chat: input row pinned under the chat log */
.chat-input-row { align-items: flex-end !important; }
.mode-switch-wrap { max-width: 170px !important; margin-left: auto !important; flex-grow: 0 !important; }
.mode-switch { max-width: 160px !important; margin-left: auto !important; }
.mode-switch-wrap label { font-size: 0.85em !important; }
"""


def _load_generator():
    """Load app/generate_surf_break.py without requiring app/ to be a package."""
    spec = importlib.util.spec_from_file_location(
        "surf_break_generator", GENERATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load generator from {GENERATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_forecast():
    """Load app/surf_forecast.py without requiring app/ to be a package."""
    spec = importlib.util.spec_from_file_location(
        "surf_forecast_mod", FORECAST_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load forecast module from {FORECAST_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_report():
    """Load app/generate_surf_report.py without requiring app/ to be a package."""
    spec = importlib.util.spec_from_file_location(
        "surf_report_generator", REPORT_PATH
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load report generator from {REPORT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_agent():
    """Load app/agent.py without requiring app/ to be a package."""
    spec = importlib.util.spec_from_file_location("surf_agent_mod", AGENT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load surf agent from {AGENT_PATH}")
    module = importlib.util.module_from_spec(spec)
    # Register before exec: app/agent.py defines @dataclass types at import
    # time, and dataclasses looks up sys.modules[cls.__module__] while the
    # class body executes. Without this, exec raises
    # "AttributeError: 'NoneType' object has no attribute '__dict__'".
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _empty_forecast_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No forecast data", showarrow=False, font={"size": 16})
    return fig


_NO_BREAK_HEADER = "### No break selected — pick one in the break book tab."

_NO_REPORT_MD = "_No report yet — pick a break to auto-load the forecast, then generate the report._"

BROWSE_INTRO = (
    "a guide to australian surf breaks — browse 238 breaks on the **break book** page, "
    "then score the week ahead + get an ai write-up on the **swell check** page, "
    "or switch to **agentic mode** above to chat with the surf agent."
)
AGENT_INTRO = (
    "agentic mode — chat with the surf agent below. "
    "charts + leaderboard stay hidden until the agent actually scores a spot."
)

AGENT_MODE_LABEL = "agentic mode"


def on_mode_change(agentic: bool):
    """Toggle between browse UI and the agent-only interface (slide switch)."""
    is_agent = bool(agentic)
    return (
        gr.update(visible=not is_agent),
        gr.update(visible=is_agent),
        AGENT_INTRO if is_agent else BROWSE_INTRO,
    )


def go_to_forecast():
    """Leave agentic mode and jump the browse tabs to the forecast page."""
    return (
        gr.Tabs(selected="forecast"),
        gr.update(value=False),
        gr.update(visible=True),
        gr.update(visible=False),
        BROWSE_INTRO,
    )


def load_breaks(path: Path = DATA_PATH) -> pd.DataFrame:
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        # Legacy format: {"name | state | region": {...}} mapping.
        df = pd.read_json(path, orient="index")
    else:
        df = pd.DataFrame(data)
    if "error" in df.columns:
        df = df[df["error"].isna()].drop(columns=["error"])
    return df.reset_index(drop=True)


def filter_breaks(
    df: pd.DataFrame,
    state: str | None = None,
    region: str | None = None,
    skill: str | None = None,
) -> pd.DataFrame:
    """Filter breaks by state / region / skill level ("All"/None = no filter)."""
    out = df
    if state and state != ALL:
        out = out[out["state"].str.lower() == state.lower()]
    if region and region != ALL:
        out = out[out["region"].str.lower() == region.lower()]
    if skill and skill != ALL:
        out = out[out["skillLevel"].str.lower() == skill.lower()]
    return out.reset_index(drop=True)


def _lat(break_: dict) -> float | None:
    try:
        return float(break_["location"]["coordinates"]["lat"])
    except (KeyError, TypeError, ValueError):
        return None


def _lng(break_: dict) -> float | None:
    try:
        return float(break_["location"]["coordinates"]["lng"])
    except (KeyError, TypeError, ValueError):
        return None


def _zoom_for_span(span: float) -> float:
    """Pick a map zoom level that fits a lat/lng degree span."""
    if span > 25:
        return 3.5
    if span > 12:
        return 4.2
    if span > 6:
        return 5.0
    if span > 3:
        return 6.0
    if span > 1.5:
        return 7.0
    if span > 0.7:
        return 8.0
    if span > 0.3:
        return 9.0
    return 10.0


AUSTRALIA_CENTER = {"lat": -25.5, "lon": 134.0}
AUSTRALIA_ZOOM = 3.5


def build_map(records: list[dict], default_view: bool = False) -> go.Figure:
    """Scattermap of breaks; point order matches ``records`` order.

    Recenters (and zooms) to fit the given records, so filtering
    reframes the map on the matching spots — unless ``default_view``
    is set, which frames the whole of Australia.
    """
    lats = [_lat(r) for r in records]
    lngs = [_lng(r) for r in records]
    names = [r.get("name", "?") for r in records]
    skills = [str(r.get("skillLevel", "?")) for r in records]
    regions = [r.get("region", "?") for r in records]

    valid = [(la, lo) for la, lo in zip(lats, lngs) if la is not None and lo is not None]
    if valid and not default_view:
        center_lat = sum(la for la, _ in valid) / len(valid)
        center_lng = sum(lo for _, lo in valid) / len(valid)
        span = max(
            max(la for la, _ in valid) - min(la for la, _ in valid),
            max(lo for _, lo in valid) - min(lo for _, lo in valid),
        )
        zoom = _zoom_for_span(span)
    else:
        center_lat, center_lng, zoom = (
            AUSTRALIA_CENTER["lat"],
            AUSTRALIA_CENTER["lon"],
            AUSTRALIA_ZOOM,
        )

    fig = go.Figure()
    if records:
        # One trace per skill level so the map gets a skill-level legend
        # on top (a single trace with per-point colours shows no legend).
        by_skill: dict[str, list[int]] = {}
        for i, s in enumerate(skills):
            by_skill.setdefault(s.lower(), []).append(i)
        ordered = [s for s in SKILL_ORDER if s in by_skill]
        ordered += [s for s in by_skill if s not in SKILL_ORDER]
        for skill_key in ordered:
            idx = by_skill[skill_key]
            # Preserve the canonical label casing from the first record.
            label = skills[idx[0]]
            fig.add_trace(
                go.Scattermap(
                    lat=[lats[i] for i in idx],
                    lon=[lngs[i] for i in idx],
                    mode="markers",
                    marker={
                        "size": 10,
                        "color": SKILL_COLORS.get(skill_key, "#1f77b4"),
                    },
                    text=[names[i] for i in idx],
                    customdata=[(names[i], regions[i], skills[i]) for i in idx],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b><br>"
                        "%{customdata[1]} · %{customdata[2]}"
                        "<extra></extra>"
                    ),
                    name=label,
                )
            )
    fig.update_layout(
        map_style="open-street-map",
        hovermode="closest",
        height=550,
        margin={"l": 0, "r": 0, "t": 30, "b": 0},
        map=dict(center={"lat": center_lat, "lon": center_lng}, zoom=zoom),
        showlegend=True,
        legend={"orientation": "h", "y": 1.02, "x": 0},
    )
    if not records:
        fig.add_annotation(
            text="No spots match these filters",
            showarrow=False,
            font={"size": 16},
        )
    return fig


def build_map_with_custom(
    base_records: list[dict], custom: dict | None, default_view: bool = False
) -> go.Figure:
    """Base map plus a gold highlight marker for the session-only custom break."""
    fig = build_map(base_records, default_view=default_view)
    if custom:
        la, lo = _lat(custom), _lng(custom)
        if la is not None and lo is not None:
            name = custom.get("name", "?")
            fig.add_trace(
                go.Scattermap(
                    lat=[la],
                    lon=[lo],
                    mode="markers",
                    marker={
                        "size": 20,
                        "color": CUSTOM_MARKER_COLOR,
                        "symbol": "star",
                    },
                    text=[f"{name} (your break)"],
                    hovertemplate=f"<b>{name}</b><br>your generated break<extra></extra>",
                    name="Your break",
                )
            )
    return fig


def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def break_to_table(break_: dict) -> pd.DataFrame:
    """Flatten one break record into a Field/Value table."""
    loc = break_.get("location", {}) or {}
    coords = loc.get("coordinates", {}) or {}
    swell = break_.get("idealSwell", {}) or {}
    swell_size = swell.get("sizeRangeFt", {}) or {}
    wind = break_.get("idealWind", {}) or {}
    tide = break_.get("idealTide", {}) or {}
    rows = [
        ("Name", break_.get("name", "")),
        ("State", break_.get("state", "")),
        ("Region", break_.get("region", "")),
        ("Description", break_.get("description", "")),
        ("Skill level", break_.get("skillLevel", "")),
        ("Break type", break_.get("breakType", "")),
        ("Peak type", break_.get("peakType", "")),
        ("Latitude", coords.get("lat", "")),
        ("Longitude", coords.get("lng", "")),
        ("Ideal swell", _join(swell.get("direction", ""))),
        ("Swell size (ft)", f"{swell_size.get('min', '?')}–{swell_size.get('max', '?')}"),
        ("Ideal wind", f"{_join(wind.get('direction', ''))} ({wind.get('type', '')})"),
        ("Ideal tide", _join(tide.get("stage", ""))),
        ("Best season", _join(break_.get("bestSeason", ""))),
        ("Hazards", _join(break_.get("hazards", ""))),
        ("Crowd", break_.get("crowdFactor", "")),
    ]
    return pd.DataFrame(rows, columns=["Field", "Value"])


DF = load_breaks()
STATES = sorted(DF["state"].dropna().unique().tolist())
REGIONS_BY_STATE = {
    state: sorted(DF[DF["state"] == state]["region"].dropna().unique().tolist())
    for state in STATES
}
ALL_REGIONS = sorted(DF["region"].dropna().unique().tolist())
SKILLS = [s for s in SKILL_ORDER if s in set(DF["skillLevel"].str.lower())] or sorted(
    DF["skillLevel"].dropna().unique().tolist()
)


def _records(df: pd.DataFrame) -> list[dict]:
    return df.to_dict(orient="records")


def _effective_names(base_records: list[dict], custom: dict | None) -> list[str]:
    names = [r.get("name", "?") for r in base_records]
    if custom and custom.get("name"):
        names = [*names, f"{custom['name']} ⭐ (your break)"]
    return names


def _break_list_label(names: list[str]) -> str:
    """Break-checklist label with the live spot count folded in."""
    return f"Breaks (pick one for details) — {len(names)} spot(s)"


def _resolve_pick(break_label: str, base_records: list[dict], custom: dict | None) -> dict | None:
    """Map a Break-list label back to its record (custom break has a ⭐ suffix)."""
    if custom and break_label == f"{custom.get('name', '')} ⭐ (your break)":
        return custom
    for r in base_records:
        if r.get("name") == break_label:
            return r
    return None


def update_map(state: str, region: str, skill: str, custom: dict | None):
    """Re-filter, rebuild the map (with custom highlight), refresh break choices.

    The spot count lives in the break-checklist label (no separate count
    display) and both tab pickers (break book + swell check) get the same
    choices so users can iterate forecasts without switching tabs.
    """
    df = filter_breaks(DF, state, region, skill)
    records = _records(df)
    unfiltered = all(v in (None, ALL) for v in (state, region, skill))
    fig = build_map_with_custom(records, custom, default_view=unfiltered)
    names = _effective_names(records, custom)
    label = _break_list_label(names)
    picker_update = gr.update(choices=names, value=None, label=label)
    return (
        fig,
        picker_update,
        picker_update,
        records,
        pd.DataFrame(columns=["Field", "Value"]),
    )


def update_region_choices(state: str):
    regions = REGIONS_BY_STATE.get(state, ALL_REGIONS) if state != ALL else ALL_REGIONS
    return gr.update(choices=[ALL, *regions], value=ALL)


def update_custom_regions(state: str):
    regions = REGIONS_BY_STATE.get(state, ALL_REGIONS)
    return gr.update(choices=[*regions], value=None)


def sync_custom_from_filters(state: str, region: str):
    """Push the main map State/Region filters into the generation form.

    A specific filter value overwrites the custom form so the wave-data
    generation function (``generate_surf_break``) runs in the same filtered
    context as the map; ``ALL`` leaves that field untouched (``gr.skip``).
    """
    if state and state != ALL:
        regions = REGIONS_BY_STATE.get(state, ALL_REGIONS)
        state_update = gr.update(value=state)
    else:
        regions = ALL_REGIONS
        state_update = gr.skip()
    if region and region != ALL:
        choices = [*regions] if region in regions else [*regions, region]
        region_update = gr.update(choices=choices, value=region)
    else:
        region_update = gr.update(choices=[*regions])
    return state_update, region_update


def on_break_pick(break_label: str, records: list[dict], custom: dict | None):
    """Update details + shared forecast state when either break list changes.

    Also refreshes the forecast-tab header and both skill defaults (the
    forecast dropdown and the agent-tab skill), and mirrors the pick into
    the other tab's checklist so both pages stay consistent. Works for
    base records and the custom ⭐ break via ``_resolve_pick``.
    """
    empty_details = pd.DataFrame(columns=["Field", "Value"])
    if not break_label:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip(), gr.skip(), gr.skip(), gr.skip()
    record = _resolve_pick(break_label, records or [], custom)
    if record is None:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip(), gr.skip(), gr.skip(), gr.skip()
    raw_skill = str(record.get("skillLevel") or "intermediate").strip().lower()
    skill_value = raw_skill if raw_skill in SKILL_ORDER else "intermediate"
    # The agent skill dropdown has no "pro-only" tier — map it to expert.
    agent_skill_value = "expert" if skill_value == "pro-only" else skill_value
    header = (
        f"### {record.get('name', '?')} — "
        f"{record.get('region', '?')}, {record.get('state', '?')}"
    )
    pick_update = gr.update(value=break_label)
    return (
        break_to_table(record),
        record,
        header,
        gr.update(value=skill_value),
        gr.update(value=agent_skill_value),
        pick_update,
        pick_update,
    )


def _telemetry(lines: list[str]) -> str:
    return "\n".join(lines)


def generate_custom_break(
    break_name: str,
    custom_state: str,
    custom_region: str,
    base_records: list[dict],
    existing_custom: dict | None,
    filter_state: str = ALL,
    filter_region: str = ALL,
    progress=gr.Progress(),
):
    """Generate one session-only break via app/generate_surf_break.py.

    The main map State/Region filters flow through here: an empty custom
    field falls back to the active map filter so the wave-data generation
    function (``generate_surf_break``) always runs in the filtered context.
    An explicitly typed custom value still takes precedence.
    Yields progressive (log, details, map, dropdown, state) tuples so the
    telemetry panel streams the tool-call process live. Only one custom
    break exists per session — a new generation replaces the old one, and
    it is never written to disk (gr.State dies with the session).
    """
    logs: list[str] = []
    empty_details = pd.DataFrame(columns=["Field", "Value"])

    def emit(fig=None, details=None, choices=None):
        return (
            _telemetry(logs),
            details if details is not None else empty_details,
            fig if fig is not None else gr.skip(),
            choices if choices is not None else gr.skip(),
            choices if choices is not None else gr.skip(),
            gr.skip(),
        )

    break_name = (break_name or "").strip()
    raw_state = (custom_state or "").strip()
    raw_region = (custom_region or "").strip()
    # Fall back to the main map filters when the custom field is empty.
    state = raw_state
    if not state and filter_state and filter_state != ALL:
        state = filter_state
        logs.append(f"↪ Using map filter state='{state}'.")
    region = raw_region
    if not region and filter_region and filter_region != ALL:
        region = filter_region
        logs.append(f"↪ Using map filter region='{region}'.")
    if not break_name or not state or not region:
        logs.append("⚠️ Enter a break name, state, and region first.")
        yield emit()
        return

    note = (
        "ℹ️ One custom break per session — generating again replaces it. "
        "Session-only: never saved to data/, deleted when the session ends."
    )
    if existing_custom:
        logs.append(f"♻️ Replacing previous session break '{existing_custom.get('name', '?')}'.")
    logs.append(note)
    t0 = time.time()
    logs.append(
        f"🔧 [tool: build_surf_break_prompt] name='{break_name}' "
        f"state='{state}' region='{region}' + schema/example from data/."
    )
    progress(0.15, desc="Building prompt…")
    yield emit()

    try:
        gen = _load_generator()
        logs.append(
            f"🧠 [tool: generate_surf_break] InferenceClient "
            f"provider='{gen.PROVIDER}' model='{gen.MODEL_ID}' "
            f"(single-shot structured JSON, temp=0.4, max_tokens=2048)…"
        )
        progress(0.4, desc="Calling surf-break generator…")
        yield emit()

        generated = gen.generate_surf_break(
            break_name=break_name, state=state, region=region
        )
        logs.append(
            "📦 [tool: extract_json] Stripped fences / outermost {…}, parsed JSON "
            f"keys={sorted(generated.keys())}."
        )
        progress(0.75, desc="Validating result…")
        yield emit()

        custom = {
            "id": f"session-only | {break_name} | {state} | {region}",
            "state": state,
            "region": region,
            **generated,
        }
        custom["state"] = state
        custom["region"] = region
        loc = dict(custom.get("location") or {})
        loc["state"] = state
        loc["region"] = region
        custom["location"] = loc

        lat, lng = _lat(custom), _lng(custom)
        dt = time.time() - t0
        logs.append(
            f"✅ Done in {dt:.1f}s → '{custom.get('name', break_name)}' "
            f"({custom.get('skillLevel', '?')}, {custom.get('breakType', '?')}) "
            f"@ lat={lat}, lng={lng}. Added to map ⭐ (session-only)."
        )
        progress(1.0, desc="Done")
        fig = build_map_with_custom(base_records or [], custom)
        details = break_to_table(custom)
        names = _effective_names(base_records or [], custom)
        picker_update = gr.update(
            choices=names,
            value=f"{custom.get('name', '')} ⭐ (your break)",
            label=_break_list_label(names),
        )
        yield (
            _telemetry(logs),
            details,
            fig,
            picker_update,
            picker_update,
            custom,
        )
    except Exception as e:  # noqa: BLE001 — surface generator errors in the telemetry panel
        logs.append(f"❌ Generation failed: {e}")
        logs.append("💡 Check HF_TOKEN is set and the inference provider serves the model.")
        yield emit()


def clear_custom_break(base_records: list[dict], selected: dict | None = None):
    """Delete the session-only break and rebuild the base map.

    If the deleted custom break was the forecast selection, the shared
    ``selected_break`` state (and forecast header) is cleared too;
    otherwise both are left untouched.
    """
    fig = build_map(base_records or [], default_view=False)
    names = [r.get("name", "?") for r in (base_records or [])]
    was_selected_custom = bool(
        selected and str(selected.get("id", "")).startswith("session-only")
    )
    picker_update = gr.update(choices=names, value=None, label=_break_list_label(names))
    return (
        None,
        "🗑️ Session break deleted.",
        pd.DataFrame(columns=["Field", "Value"]),
        fig,
        picker_update,
        picker_update,
        None if was_selected_custom else gr.skip(),
        _NO_BREAK_HEADER if was_selected_custom else gr.skip(),
        gr.skip(),
    )


def fetch_forecast(
    selected_break: dict | None,
    skill: str,
    progress=gr.Progress(),
):
    """Stage 1 — deterministic forecast only: score + build the 3 charts.

    Delegates to ``app/surf_forecast.get_scored_week`` (Open-Meteo +
    deterministic scoring) and builds score / swell / wind figs. No LLM
    call here, so the graphs render immediately and the user can inspect
    them before opting into Stage 2 (``generate_reports``). Runs
    automatically on break pick / skill change (no button). Yields
    (status, score_fig, waves_fig, wind_fig, scored_payload,
    telemetry, report_md) tuples — report_md is always reset so a stale
    report never lingers after a new fetch. The LLM never owns numbers —
    it only narrates these scores in Stage 2.
    """
    logs: list[str] = []

    def emit(status, score_fig, waves_fig, wind_fig, payload):
        return (
            status,
            score_fig,
            waves_fig,
            wind_fig,
            payload,
            _telemetry(logs),
            _NO_REPORT_MD,
        )

    if not selected_break:
        logs.append("⚠️ No break selected — pick one in the break list above.")
        yield emit(
            "⚠️ Pick a break in the list above first.",
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            None,
        )
        return
    try:
        days_int = 7
        t0 = time.time()
        logs.append(
            f"🔧 [tool: get_scored_week] break='{selected_break.get('name', '?')}' "
            f"skill='{skill}' days={days_int} (Open-Meteo marine+wind → scoring.score_week)."
        )
        progress(0.15, desc="Fetching + scoring forecast…")
        yield emit(
            "⏳ Fetching + scoring forecast…",
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            None,
        )

        mod = _load_forecast()
        result = mod.get_scored_week(
            selected_break, skill=skill, days=days_int
        )
        scored = result.get("scored", []) or []
        skill_used = result.get("skill", skill)
        spot = result.get("spot", {})
        progress(0.6, desc="Building charts…")
        score_fig = mod.build_score_fig(scored)
        waves_fig = mod.build_waves_fig(scored)
        wind_fig = mod.build_wind_fig(scored, spot)
        try:
            sun = result.get("sun") or {}
            score_fig = mod.add_sun_markers(score_fig, sun)
            waves_fig = mod.add_sun_markers(waves_fig, sun)
        except AttributeError:
            sun = {}
            pass
        best = mod.best_window(scored)
        daily = mod.daily_best(scored)
        dt = time.time() - t0
        logs.append(
            f"📊 [tool: score_week] {len(scored)} hour(s) scored "
            f"(skill={skill_used}, daily bests={len(daily)}) in {dt:.1f}s."
        )
        progress(1.0, desc="Charts ready")
        if not scored:
            logs.append("⚠️ No scored hours — charts are empty, report disabled.")
            yield emit(
                f"⚠️ {selected_break.get('name', '?')} · no scored hours ({days_int}d).",
                score_fig,
                waves_fig,
                wind_fig,
                None,
            )
            return

        logs.append(
            "✅ Charts ready — inspect them above, then press "
            "“Generate surf report ✨” for the write-up (one sentence per day + recommendation)."
        )
        status = (
            f"✅ {selected_break.get('name', '?')} · "
            f"skill {skill_used} · "
            f"{len(scored)} hour(s) scored ({days_int}d). "
            f"Charts ready — generate the report when ready."
        )
        wetsuit = result.get("wetsuit_hint")
        if wetsuit:
            status += f" 🤿 {wetsuit}."
        payload = {
            "break": selected_break,
            "skill": skill_used,
            "spot": spot,
            "scored": scored,
            "daily": daily,
            "best": best,
            "days": days_int,
            "sun": result.get("sun") or {},
            "sst_c": result.get("sst_c"),
            "wetsuit_hint": result.get("wetsuit_hint"),
        }
        yield emit(status, score_fig, waves_fig, wind_fig, payload)
    except Exception as e:  # noqa: BLE001 — surface fetch/score errors in the status box
        logs.append(f"❌ Forecast failed: {e}")
        yield emit(
            f"❌ Forecast failed: {e}",
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            None,
        )


def generate_reports(
    scored_payload: dict | None,
    progress=gr.Progress(),
):
    """Stage 2 — short narrated report, streamed live as plain markdown.

    Reads the ``scored_payload`` saved by :func:`fetch_forecast` and calls
    ``app/generate_surf_report.generate_surf_report_stream`` (same
    InferenceClient framework/model as break generation, ``stream=True``).
    The prompt carries only the daily bests (<=7 lines) + best window, and
    the model returns one dot-point per day (one full sentence of outlook
    per day) plus a ``**Recommendation: ...**``
    line — small prompt + short output keeps time-to-first-token low. Yields
    (report_md, telemetry) tuples; the streamed text IS the report, so no
    parse step. The LLM narrates the provided scores only.
    """
    logs: list[str] = []

    def emit(report_md):
        return (report_md, _telemetry(logs))

    daily = (scored_payload or {}).get("daily") or []
    if not scored_payload or not daily:
        logs.append("⚠️ No scored forecast yet — pick a break first.")
        yield emit("_No report yet — pick a break to auto-load the forecast first._")
        return

    # Instant feedback first: this yield renders before any network wait,
    # so the button never looks dead while the model spins up.
    logs.append(
        f"🔧 [tool: build_surf_report_prompt] {len(daily)} daily bests + "
        f"best window → tiny prompt (no hourly rows)."
    )
    progress(0.1, desc="Contacting report model…")
    yield emit("_Contacting report model… watch the telemetry box below for progress._")

    try:
        rep = _load_report()
        logs.append(
            f"🧠 [tool: generate_surf_report_stream] InferenceClient "
            f"provider='{rep.PROVIDER}' model='{rep.MODEL_ID}' "
            f"(stream=True, temp={rep.TEMPERATURE}, max_tokens={rep.MAX_TOKENS}, "
            f"reasoning disabled via extra_body={rep.EXTRA_BODY} + /no_think)…"
        )
        progress(0.3, desc="Writing surf report…")

        t0 = time.time()
        text = ""
        shown = ""
        chunk_count = 0
        first_content_at: float | None = None
        last_heartbeat = t0
        stream_stats: dict = {}
        for text in rep.generate_surf_report_stream(
            break_=scored_payload["break"],
            skill=scored_payload["skill"],
            daily=daily,
            best=scored_payload.get("best"),
            days=scored_payload.get("days", len(daily)),
            stats=stream_stats,
        ):
            chunk_count += 1
            # Only real report words go in the report box — the cleaner's
            # pre-marker output is "" (thinking stripped), so re-yielding
            # every chunk just flickered an empty box with a fake bar.
            if text.strip() and text != shown:
                shown = text
                if first_content_at is None:
                    first_content_at = time.time()
                    logs.append(
                        f"📝 First report words in {first_content_at - t0:.1f}s "
                        "— writing below."
                    )
                yield emit(shown)
            else:
                # While waiting for real words, heartbeat the telemetry
                # box so the UI visibly works (chunk count + elapsed).
                now = time.time()
                if now - last_heartbeat >= 5.0:
                    last_heartbeat = now
                    logs.append(
                        f"⏳ Receiving… {chunk_count} chunk(s), "
                        f"{now - t0:.0f}s elapsed."
                    )
                    yield emit(
                        shown
                        or "_Writing report… progress is in the telemetry box below._"
                    )
        if not shown.strip():
            if chunk_count:
                logs.append(
                    f"⏳ Stream ended with {chunk_count} chunk(s) but no "
                    "report words survived cleaning."
                )
            raise ValueError(
                "Empty stream from report generator "
                f"(reasoning_chars={stream_stats.get('reasoning_chars', '?')}, "
                f"content_chars={stream_stats.get('content_chars', '?')})."
            )
        text = shown

        dt = time.time() - t0
        logs.append(
            f"✅ Done in {dt:.1f}s → {chunk_count} chunk(s), "
            f"final report {len(text)} chars "
            f"(content={stream_stats.get('content_chars', '?')} chars, "
            f"hidden reasoning={stream_stats.get('reasoning_chars', '?')} chars — "
            f"what you see above is the final report, not the thinking)."
        )
        progress(1.0, desc="Done")
        yield emit(text)
    except Exception as e:  # noqa: BLE001 — LLM failure keeps deterministic charts
        logs.append(f"❌ Report generation failed: {e}")
        logs.append("💡 Check HF_TOKEN is set and the inference provider serves the model.")
        logs.append("ℹ️ Charts above are deterministic and still valid.")
        yield emit("_Report generation failed — charts above still apply._")


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
    """Coerce a rank_spots_this_week tool_result payload to a row list.

    Accepts a list of dicts directly, a JSON string, or a Python-repr
    string (``str(list)`` as captured by the wavereader trace), plus a
    ``{"rank": [...]}`` wrapper as an object or JSON string. Returns
    None when not a rank payload.
    """
    if isinstance(payload, dict) and isinstance(payload.get("rank"), list):
        payload = payload["rank"]
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
            elif name == "rank_spots_this_week":
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
    """Format a rank_spots_this_week payload as a leaderboard dataframe."""
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
    if name == "rank_spots_this_week":
        rows = _coerce_rank_rows(payload)
        if rows:
            top = rows[0]
            return (
                f"{len(rows)} spot(s) ranked "
                f"(top: {top.get('name', '?')} {top.get('best_score', '?')}/10)"
            )
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
    mod = _load_forecast()
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
    mod = _load_forecast()
    waves_fig = mod.build_waves_fig(hours)
    wind_fig = mod.build_wind_fig(hours, spot)
    best_md = _format_forecast_best(hours, label)
    return waves_fig, wind_fig, best_md


def _format_pref_chip(
    pref_state: str | None,
    pref_region: str | None,
    skill: str | None,
    stance: str | None,
    selected_break: dict | None,
) -> str:
    """Render the surf-agent context chip (active prefs + encyclopedia pick)."""
    state = pref_state if pref_state and pref_state != ALL else "All"
    region = pref_region if pref_region and pref_region != ALL else "All"
    skill_txt = (skill or "intermediate").strip().lower()
    stance_txt = (stance or "no preference").strip().lower()
    if selected_break and selected_break.get("name"):
        ctx = ", ".join(
            p
            for p in (
                selected_break.get("name"),
                selected_break.get("region"),
                selected_break.get("state"),
            )
            if p
        )
        viewing = ctx or selected_break.get("name")
    else:
        viewing = "none"
    return (
        f"_Prefs: state={state} · region={region} · skill={skill_txt} · "
        f"stance={stance_txt} · viewing={viewing}_"
    )


HISTORY_PREPEND_TURNS = 6


def on_agent_spot_change(spot_label: str | None, charts_state: dict | None,
                         selected_break: dict | None):
    """Rebuild the agent-tab charts for the spot picked in the dropdown."""
    spots = (charts_state or {}).get("spots") or []
    entry = next((s for s in spots if s.get("label") == spot_label), None)
    if entry is None:
        return gr.skip(), gr.skip(), gr.skip(), gr.skip()
    try:
        mod = _load_forecast()
        scored = entry["hours"]
        spot = _resolve_spot_for_entry(entry, selected_break, mod)
        label = entry.get("label")
        skill = entry.get("skill")
        score_fig, waves_fig, wind_fig, best_md = _build_chart_trio(
            scored, spot, label, skill
        )
        return score_fig, waves_fig, wind_fig, best_md
    except Exception:  # noqa: BLE001 — keep the current charts on failure
        return gr.skip(), gr.skip(), gr.skip(), gr.skip()


def chat_fn(
    message: str,
    history: list[dict] | None,
    skill: str,
    hf_token: str,
    selected_break: dict | None,
    pref_state: str | None = None,
    pref_region: str | None = None,
    stance: str | None = None,
    pref_skill: str | None = None,
    agent_session=None,
    agent_token_used: str | None = None,
    agent_conv: list[dict] | None = None,
    agent_charts: dict | None = None,
    daypart: str | None = None,
    progress=gr.Progress(),
):
    """Chat with a session-persistent SurfAgent, then chart every payload.

    The ``agent_session`` gr.State holds one SurfAgent per user session so
    follow-ups reuse the smolagents conversation memory instead of
    starting fresh. A changed ``hf_token`` (or a missing session) rebuilds
    the agent; on a rebuild the last ``HISTORY_PREPEND_TURNS`` turns from
    ``agent_conv`` are prepended to the question explicitly. Streams
    ``run_stream`` events, then renders ALL score_week payloads in the
    trace (spot dropdown when >1), swell + wind charts for get_forecast
    payloads, plus the rank leaderboard when a
    rank_spots_this_week payload exists. The textbox is cleared via the
    second output (``""``).
    Yields (chatbot, msg_box, telemetry, status, score_fig, waves_fig,
    wind_fig, best_md, spot_dd, rank_df, charts, session, token_used,
    conv, charts_visible, rank_visible) tuples.
    """
    history = list(history or [])
    agent_conv = list(agent_conv or [])
    logs: list[str] = []
    message = (message or "").strip()

    def emit(status, score_fig=gr.skip(), waves_fig=gr.skip(), wind_fig=gr.skip(),
             best_md=gr.skip(), spot_dd=gr.skip(), rank_df=gr.skip(),
             charts=gr.skip(), session=gr.skip(), token_used=gr.skip(),
             conv=gr.skip(), charts_visible=gr.skip(), rank_visible=gr.skip()):
        return (
            history,
            "",
            _telemetry(logs),
            status,
            score_fig,
            waves_fig,
            wind_fig,
            best_md,
            spot_dd,
            rank_df,
            charts,
            session,
            token_used,
            conv,
            charts_visible,
            rank_visible,
        )

    if not message:
        logs.append("⚠️ Type a question first.")
        yield emit("⚠️ Type a question first.")
        return

    skill = (pref_skill or skill or "intermediate").strip().lower()
    hint_bits = [f"surfer skill level = {skill}"]
    # Encyclopedia pick wins over pref state/region; explicit pref wins over ALL.
    sel_state = (selected_break or {}).get("state") if selected_break else None
    sel_region = (selected_break or {}).get("region") if selected_break else None
    eff_state = sel_state or (
        pref_state if pref_state and pref_state != ALL else None
    )
    eff_region = sel_region or (
        pref_region if pref_region and pref_region != ALL else None
    )
    if eff_state:
        hint_bits.append(f"state={eff_state}")
    if eff_region:
        hint_bits.append(f"region={eff_region}")
    if selected_break:
        context = ", ".join(
            p for p in (
                selected_break.get("name"),
                selected_break.get("region"),
                selected_break.get("state"),
            ) if p
        )
        if context:
            hint_bits.append(f"User is viewing {context}.")
    stance_norm = (stance or "no preference").strip().lower()
    if stance_norm and stance_norm != "no preference":
        hint_bits.append(
            f"stance={stance_norm} (goofy prefers lefts, natural prefers rights, "
            "a-frame neutral; affects break advice, not scores)"
        )
    daypart_norm = (daypart or "all day").strip().lower()
    if daypart_norm == "mornings":
        hint_bits.append(
            "prefer morning windows: use find_best_windows(daypart=\"morning\") "
            "for each candidate spot"
        )
    elif daypart_norm == "weekend":
        hint_bits.append(
            "weekend only: use find_best_windows(weekend_only=True) "
            "for each candidate spot"
        )
    hint = "\n[" + "; ".join(hint_bits) + "]"
    token_key = (hf_token or "").strip()
    fresh = agent_session is None or (agent_token_used or "") != token_key
    if fresh and agent_conv:
        convo_lines = []
        for turn in agent_conv[-HISTORY_PREPEND_TURNS:]:
            q = str(turn.get("q", "")).strip()
            a = str(turn.get("a", "")).strip()
            if q:
                convo_lines.append(f"User: {q}")
            if a:
                convo_lines.append(f"Assistant: {a[:800]}")
        convo_block = "\n".join(convo_lines)
        question = f"Conversation so far:\n{convo_block}\n\nFollow-up: {message}{hint}"
    else:
        question = message + hint

    history = [*history,
               {"role": "user", "content": message},
               {"role": "assistant", "content": ""}]
    if fresh:
        logs.append(f"🧠 [agent] Starting new SurfAgent session (skill={skill})…")
    else:
        logs.append(f"🧠 [agent] Reusing session SurfAgent (skill={skill})…")
    progress(0.1, desc="Contacting surf agent…")
    yield emit("⏳ Agent thinking…")

    try:
        agent_mod = _load_agent()
    except Exception as e:  # noqa: BLE001 — sibling module not ready yet
        logs.append(f"❌ Surf agent module not available: {e}")
        history[-1]["content"] = (
            "_The surf agent isn't available yet (app/agent.py failed to load)._"
        )
        yield emit("❌ Surf agent module not available.")
        return

    if fresh:
        try:
            token = token_key or None  # None → HF_TOKEN env is used
            agent_session = agent_mod.SurfAgent(hf_token=token)
            agent_token_used = token_key
        except ValueError as e:
            if "HF_TOKEN" in str(e):
                logs.append("⚠️ No HF token — set HF_TOKEN env or paste a token above.")
                history[-1]["content"] = (
                    "_No Hugging Face token found._ Paste one in the **HF token** box "
                    "(per-session override, never logged) or set `HF_TOKEN` in your "
                    "environment, then ask again. Get a token at "
                    "https://huggingface.co/settings/tokens."
                )
                yield emit("⚠️ No HF token — paste one above or set HF_TOKEN.")
                return
            raise
        except Exception as e:  # noqa: BLE001 — friendly chat message, not a crash
            logs.append(f"❌ Could not start surf agent: {e}")
            history[-1]["content"] = f"_Could not start the surf agent: {e}_"
            yield emit(f"❌ Could not start surf agent: {e}")
            return
    agent = agent_session

    tool_count = 0
    live_spots: list[dict] = []
    live_rank: list[dict] | None = None
    live_forecasts: list[dict] = []
    pending_score_args: list[dict] = []
    pending_forecast_args: list[dict] = []
    try:
        progress(0.3, desc="Streaming agent answer…")
        for kind, payload in agent.run_stream(question):
            if kind == "model":
                history[-1]["content"] += payload
                suffix = f" ({tool_count} tool(s) so far)" if tool_count else ""
                if live_spots:
                    suffix += f" · 📊 {live_spots[-1]['label']}"
                yield emit(f"💬 Streaming answer…{suffix}")
            elif kind == "tool":
                # Backward-compat alias fired just before tool_start.
                tool_count += 1
                name = str(payload)
                logs.append(f"🔧 [tool: {name}]")
                yield emit(f"🔧 Tool call {tool_count}: {name}…")
            elif kind == "tool_start":
                data = payload if isinstance(payload, dict) else {}
                name = str(data.get("name", "?"))
                args = data.get("arguments", {})
                if not isinstance(args, dict):
                    args = _parse_tool_args({"arguments": args})
                # The ("tool", name) compat event already counted this call.
                if logs and logs[-1] == f"🔧 [tool: {name}]":
                    pass
                else:
                    tool_count += 1
                    logs.append(f"🔧 [tool: {name}]")
                logs.append(f"🔧 [tool: {name}] args={_short_args(args)}")
                if name in ("score_week", "find_best_windows"):
                    pending_score_args.append(dict(args))
                elif name == "get_forecast":
                    pending_forecast_args.append(dict(args))
                human = _human_tool_status(name, args)
                progress(0.3, desc=human)
                yield emit(f"🔧 {human} (tool {tool_count})")
            elif kind == "tool_end":
                data = payload if isinstance(payload, dict) else {}
                name = str(data.get("name", "?"))
                ms = data.get("ms")
                summary = data.get("summary", "")
                if ms is not None:
                    logs.append(f"📦 [{name}] done in {ms / 1000:.1f}s → {summary}")
                else:
                    logs.append(f"📦 [{name}] → {summary}")
                # Prefer the full observation carried on the event itself
                # (CodeAgent inner-tool path); fall back to peeking the trace
                # for legacy ToolCallingAgent-style events.
                obs = data.get("observation")
                if obs is None:
                    try:
                        events = list(getattr(getattr(agent, "trace", None), "events", None) or [])
                        if events:
                            obs = (getattr(events[-1], "data", None) or {}).get("observation")
                    except Exception:  # noqa: BLE001 — progressive is best-effort
                        obs = None
                if name in ("score_week", "find_best_windows"):
                    try:
                        hours = _coerce_scored_hours(obs)
                    except Exception:  # noqa: BLE001 — keep streaming on bad payload
                        hours = None
                    if hours:
                        call_args = (
                            pending_score_args.pop(0)
                            if pending_score_args
                            else {}
                        )
                        spot_name = call_args.get("spot_name")
                        region = call_args.get("region")
                        skill_used = call_args.get("skill") or skill
                        if isinstance(obs, dict):
                            spot_info = obs.get("spot") or {}
                            spot_name = spot_name or spot_info.get("name")
                            region = region or spot_info.get("region") or spot_info.get(
                                "state"
                            )
                            skill_used = obs.get("skill") or skill_used
                        label = _live_spot_label(
                            spot_name, region, len(live_spots) + 1
                        )
                        entry = {
                            "label": label,
                            "spot_name": spot_name,
                            "region": region,
                            "skill": skill_used,
                            "hours": hours,
                        }
                        live_spots.append(entry)
                        _dedupe_spot_labels(live_spots)
                        try:
                            mod = _load_forecast()
                            spot = _resolve_spot_for_entry(
                                entry, selected_break, mod
                            )
                            s_fig, w_fig, wi_fig, best = _build_chart_trio(
                                hours, spot, entry["label"], skill_used
                            )
                            logs.append(
                                f"📊 [tool: score_week trace] {len(hours)} hour(s) "
                                f"charted for '{entry['label']}' (deterministic)."
                            )
                            labels = [s["label"] for s in live_spots]
                            spot_update = gr.update(
                                choices=labels,
                                value=entry["label"],
                                visible=len(labels) > 1,
                            )
                            live_charts = {
                                "spots": live_spots,
                                "forecasts": live_forecasts,
                                "rank": live_rank,
                            }
                            yield emit(
                                f"📊 Charted '{entry['label']}' ({len(hours)} hours) — "
                                "agent still thinking…",
                                s_fig,
                                w_fig,
                                wi_fig,
                                best,
                                spot_update,
                                gr.skip(),
                                live_charts,
                                gr.skip(),
                                gr.skip(),
                                gr.skip(),
                                gr.update(visible=True),
                                gr.skip(),
                            )
                        except Exception:  # noqa: BLE001 — charts fail, answer stands
                            yield emit(f"📦 {name} done — agent still thinking…")
                    else:
                        yield emit(f"📦 {name} done — agent still thinking…")
                elif name == "rank_spots_this_week":
                    try:
                        rows = _coerce_rank_rows(obs)
                    except Exception:  # noqa: BLE001 — keep streaming on bad payload
                        rows = None
                    if rows:
                        live_rank = rows
                        rank_df = _format_rank_table(rows)
                        logs.append(
                            f"🏆 [tool: rank_spots_this_week trace] {len(rows)} spot(s) "
                            f"ranked (top: {rows[0].get('name', '?')} "
                            f"{rows[0].get('best_score', '?')}/10)."
                        )
                        yield emit(
                            f"🏆 Ranked {len(rows)} spots — top: "
                            f"{rows[0].get('name', '?')} — agent still thinking…",
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            rank_df,
                            {"spots": live_spots, "forecasts": live_forecasts, "rank": live_rank},
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.skip(),
                            gr.update(visible=True),
                        )
                    else:
                        yield emit(f"📦 {name} done — agent still thinking…")
                elif name == "get_forecast":
                    try:
                        hours = _coerce_forecast_hours(obs)
                    except Exception:  # noqa: BLE001 — keep streaming on bad payload
                        hours = None
                    if hours:
                        call_args = (
                            pending_forecast_args.pop(0)
                            if pending_forecast_args
                            else {}
                        )
                        spot_name = call_args.get("spot_name")
                        region = call_args.get("region")
                        label = _live_spot_label(
                            spot_name, region, len(live_forecasts) + 1
                        )
                        entry = {
                            "label": label,
                            "spot_name": spot_name,
                            "region": region,
                            "hours": hours,
                        }
                        live_forecasts.append(entry)
                        _dedupe_spot_labels(live_forecasts)
                        try:
                            mod = _load_forecast()
                            spot = _resolve_spot_for_entry(
                                entry, selected_break, mod
                            )
                            w_fig, wi_fig, best = _build_forecast_duo(
                                hours, spot, entry["label"]
                            )
                            logs.append(
                                f"📊 [tool: get_forecast trace] {len(hours)} hour(s) "
                                f"charted for '{entry['label']}' (swell + wind, unscored)."
                            )
                            live_charts = {
                                "spots": live_spots,
                                "forecasts": live_forecasts,
                                "rank": live_rank,
                            }
                            yield emit(
                                f"📊 Charted forecast '{entry['label']}' "
                                f"({len(hours)} hours) — agent still thinking…",
                                gr.skip(),
                                w_fig,
                                wi_fig,
                                best,
                                gr.skip(),
                                gr.skip(),
                                live_charts,
                                gr.skip(),
                                gr.skip(),
                                gr.skip(),
                                gr.update(visible=True),
                                gr.skip(),
                            )
                        except Exception:  # noqa: BLE001 — charts fail, answer stands
                            yield emit(f"📦 {name} done — agent still thinking…")
                    else:
                        yield emit(f"📦 {name} done — agent still thinking…")
                else:
                    yield emit(f"📦 {name} done — agent still thinking…")
            elif kind == "code":
                # Executed code block, parsed into chat-friendly tool
                # lines. Display-only — the ("final", ...) event replaces
                # the bubble with the clean answer, so never overwrite
                # history here and never log "Answer complete" yet.
                call_lines = _parse_code_calls(payload if isinstance(payload, str) else "")
                if call_lines:
                    logs.append(f"🧾 executed: {' · '.join(c.strip('`') for c in call_lines)}")
                    yield emit(f"🧾 Ran {len(call_lines)} call(s) — reading results…")
                else:
                    yield emit("🧾 Code ran — reading results…", )
            elif kind == "final":
                # Clean final answer replaces the streamed model/code tokens.
                clean = payload if isinstance(payload, str) else str(payload or "")
                history[-1]["content"] = clean or history[-1]["content"]
                logs.append(f"✅ Answer complete ({tool_count} tool call(s)).")
                yield emit("✅ Answer complete — building charts…")
    except ValueError as e:
        if "HF_TOKEN" in str(e):
            logs.append("⚠️ No HF token — set HF_TOKEN env or paste a token above.")
            history[-1]["content"] = (
                "_No Hugging Face token found._ Paste one in the **HF token** box "
                "or set `HF_TOKEN`, then ask again."
            )
            yield emit("⚠️ No HF token — paste one above or set HF_TOKEN.")
            return
        logs.append(f"❌ Agent run failed: {e}")
        history[-1]["content"] += f"\n\n_❌ Agent run failed: {e}_"
        yield emit(f"❌ Agent run failed: {e}")
        return
    except Exception as e:  # noqa: BLE001 — keep the partial answer visible
        logs.append(f"❌ Agent run failed: {e}")
        history[-1]["content"] += f"\n\n_❌ Agent run failed: {e}_"
        yield emit(f"❌ Agent run failed: {e}")
        return

    try:
        trace = getattr(agent, "trace", None)
        for line in _build_agent_telemetry(trace, tool_count):
            if line not in logs:
                logs.append(line)
    except Exception:  # noqa: BLE001 — telemetry must not crash the chat
        pass

    final_answer = history[-1]["content"] if history else ""
    agent_conv = [*agent_conv, {"q": message, "a": final_answer}]

    try:
        chart_data = _agent_chart_data(getattr(agent, "trace", None))
    except Exception:  # noqa: BLE001 — trace parsing must not crash the chat
        chart_data = {"spots": [], "forecasts": [], "rank": None}
    spots = chart_data.get("spots") or []
    forecasts = chart_data.get("forecasts") or []
    rank = chart_data.get("rank")
    rank_df = _format_rank_table(rank)
    if rank:
        logs.append(
            f"🏆 [tool: rank_spots_this_week trace] {len(rank)} spot(s) ranked "
            f"(top: {rank[0].get('name', '?')} {rank[0].get('best_score', '?')}/10)."
        )
    if not spots and not forecasts:
        logs.append("ℹ️ No score_week/get_forecast payload in this answer — charts need a specific break.")
        yield emit(
            "💬 No scored forecast in this answer — ask for a specific break to see charts.",
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.update(choices=[], value=None, visible=False),
            rank_df,
            chart_data,
            agent_session,
            agent_token_used,
            agent_conv,
            gr.update(visible=False),
            gr.update(visible=bool(rank)),
        )
        return

    if not spots and forecasts:
        try:
            mod = _load_forecast()
            latest = forecasts[-1]
            spot = _resolve_spot_for_entry(latest, selected_break, mod)
            waves_fig, wind_fig, best_md = _build_forecast_duo(
                latest["hours"], spot, latest.get("label")
            )
            logs.append(
                f"📊 [tool: get_forecast trace] {len(latest['hours'])} hour(s) charted "
                f"for '{latest.get('label')}' (swell + wind, unscored)."
            )
            status = (
                f"✅ Forecast charts ready — {len(latest['hours'])} hour(s) "
                f"for '{latest.get('label')}' from the agent trace."
            )
            history[-1]["content"] += f"\n\n📊 _Forecast charted below: {latest.get('label')} — {best_md}_"
            agent_conv = [*agent_conv[:-1], {"q": message, "a": history[-1]["content"]}]
            yield emit(
                status,
                gr.skip(),
                waves_fig,
                wind_fig,
                best_md,
                gr.skip(),
                rank_df,
                chart_data,
                agent_session,
                agent_token_used,
                agent_conv,
                gr.update(visible=True),
                gr.update(visible=bool(rank)),
            )
        except Exception as e:  # noqa: BLE001 — charts fail, answer still stands
            logs.append(f"⚠️ Could not build forecast charts from trace: {e}")
            yield emit(
                "💬 Answer above stands — charts unavailable for this run.",
                gr.skip(),
                gr.skip(),
                gr.skip(),
                gr.skip(),
                gr.skip(),
                rank_df,
                chart_data,
                agent_session,
                agent_token_used,
                agent_conv,
                gr.update(visible=False),
                gr.update(visible=bool(rank)),
            )
        return

    try:
        mod = _load_forecast()
        first = spots[0]
        # Carry skill through when the trace payload lacks it.
        if not first.get("skill"):
            first["skill"] = skill
        spot = _resolve_spot_for_entry(first, selected_break, mod)
        score_fig, waves_fig, wind_fig, best_md = _build_chart_trio(
            first["hours"], spot, first["label"], first.get("skill")
        )
        logs.append(
            f"📊 [tool: score_week trace] {len(first['hours'])} hour(s) charted "
            f"for '{first['label']}' (deterministic — not LLM output)."
        )
        if len(spots) > 1:
            logs.append(
                f"📊 {len(spots)} scored spot(s) in this answer — "
                "pick one in the chart-spot dropdown."
            )
        labels = [s["label"] for s in spots]
        spot_update = gr.update(choices=labels, value=labels[0], visible=len(labels) > 1)
        status = (
            f"✅ Charts ready — {len(first['hours'])} scored hour(s) "
            f"for '{first['label']}' from the agent trace."
        )
        if len(spots) > 1:
            status += f" ({len(spots)} spots scored — switch via dropdown.)"
        history[-1]["content"] += f"\n\n📊 _Scored forecast charted below: {first['label']} — {best_md}_"
        agent_conv = [*agent_conv[:-1], {"q": message, "a": history[-1]["content"]}]
        yield emit(
            status,
            score_fig,
            waves_fig,
            wind_fig,
            best_md,
            spot_update,
            rank_df,
            chart_data,
            agent_session,
            agent_token_used,
            agent_conv,
            gr.update(visible=True),
            gr.update(visible=bool(rank)),
        )
    except Exception as e:  # noqa: BLE001 — charts fail, answer still stands
        logs.append(f"⚠️ Could not build charts from trace: {e}")
        yield emit(
            "💬 Answer above stands — charts unavailable for this run.",
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            rank_df,
            chart_data,
            agent_session,
            agent_token_used,
            agent_conv,
            gr.update(visible=False),
            gr.update(visible=bool(rank)),
        )


def clear_agent_chat():
    """Reset the agent tab: session agent, history, charts, leaderboard."""
    return (
        [],
        "",
        "",
        "",
        gr.skip(),
        gr.skip(),
        gr.skip(),
        "_No agent answer yet._",
        gr.update(choices=[], value=None, visible=False),
        pd.DataFrame(columns=["Rank", "Spot", "Region", "Best score", "Best time"]),
        None,
        None,
        "",
        [],
        gr.update(visible=False),
        gr.update(visible=False),
    )


def on_rank_select(evt: gr.SelectData, rank_df: pd.DataFrame):
    """Click a leaderboard row → prefill the agent box with a drill-down.

    The rank table only carries best score/time (no hourly rows), so the
    click composes a follow-up question instead of charting directly —
    the agent's score_week call then produces the graphs.
    """
    try:
        row = rank_df.iloc[evt.index[0]]
        spot = str(row.get("Spot", "") or "").strip()
        region = str(row.get("Region", "") or "").strip()
        if not spot:
            return gr.skip()
        where = f" in {region}" if region and region != "?" else ""
        return gr.update(value=f"When should I surf {spot}{where} this week?")
    except (AttributeError, IndexError, KeyError, TypeError):
        return gr.skip()


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="wave~reader — break book + swell check") as demo:
        with gr.Row(elem_classes=["header-row"]):
            with gr.Column(scale=9):
                gr.Markdown("# wave~reader", elem_classes=["hero-title"])
                intro_md = gr.Markdown(BROWSE_INTRO)
            with gr.Column(scale=1, min_width=150, elem_classes=["mode-switch-wrap"]):
                mode_toggle = gr.Checkbox(
                    value=False,
                    label=AGENT_MODE_LABEL,
                    elem_classes=["mode-switch"],
                    container=True,
                )
        records_state = gr.State(_records(DF))
        custom_state = gr.State(None)  # one session-only break; never persisted
        selected_break = gr.State(None)  # shared pick for the forecast tab
        scored_state = gr.State(None)  # stage-1 scored payload feeding stage-2 report
        agent_session = gr.State(None)  # session-persistent SurfAgent instance
        agent_token_used = gr.State("")  # hf_token key the session agent was built with
        agent_conv = gr.State([])  # explicit conversation history for fresh agents
        agent_charts = gr.State(None)  # all score_week payloads + rank payload
        with gr.Group(visible=True) as browse_group:
            with gr.Tabs() as tabs:
                with gr.Tab("break book", id="encyclopedia"):
                    gr.Markdown("### break book")
                    gr.Markdown("filter spots, hover a dot for its name, then pick a break for details.")
                    with gr.Row():
                        state_dd = gr.Dropdown([ALL, *STATES], value=ALL, label="State")
                        region_dd = gr.Dropdown([ALL, *ALL_REGIONS], value=ALL, label="Region")
                        skill_dd = gr.Dropdown([ALL, *SKILLS], value=ALL, label="Skill level")
                    with gr.Row():
                        with gr.Column(scale=3):
                            map_plot = gr.Plot(build_map(_records(DF), default_view=True), label="Spots")
                            cant_find_btn = gr.Button(
                                "Can't find your local break?", variant="primary"
                            )
                            with gr.Group(visible=False) as custom_box:
                                gr.Markdown(
                                    "### Generate your local break\n"
                                    "One break per session, generated live via "
                                    "`app/generate_surf_break.py`. Session-only — "
                                    "never saved, deleted when your session ends."
                                )
                                with gr.Row():
                                    custom_state_dd = gr.Dropdown(
                                        STATES, value=None, label="State"
                                    )
                                    custom_region_dd = gr.Dropdown(
                                        ALL_REGIONS,
                                        value=None,
                                        label="Region (or type a new one)",
                                        allow_custom_value=True,
                                    )
                                custom_name_txt = gr.Textbox(
                                    label="Break name", placeholder="e.g. Kilcunda"
                                )
                                with gr.Row():
                                    generate_btn = gr.Button("Generate my break", variant="primary")
                                    clear_btn = gr.Button("Delete my break", variant="stop")
                                telemetry_box = gr.Textbox(
                                    label="Generation telemetry (tool calls)",
                                    lines=8,
                                    max_lines=14,
                                    interactive=False,
                                    placeholder="Press “Generate my break” to see the tool-call trace…",
                                )
                        with gr.Column(scale=2):
                            break_dd = gr.Radio(
                                choices=[r.get("name", "?") for r in _records(DF)],
                                value=None,
                                label=f"Breaks (pick one for details) — {len(DF)} spot(s)",
                                elem_classes=["break-list"],
                            )
                            details_df = gr.Dataframe(
                                headers=["Field", "Value"],
                                row_count=(16, "fixed"),
                                column_count=(2, "fixed"),
                                label="Break details",
                                wrap=True,
                            )
                            go_forecast_btn = gr.Button(
                                "Check swell →", variant="primary"
                            )
                with gr.Tab("swell check", id="forecast"):
                    gr.Markdown("### swell check")
                    gr.Markdown(
                        "pick a break below — charts load automatically "
                        "+ an optional ai report."
                    )
                    fc_break_dd = gr.Radio(
                        choices=[r.get("name", "?") for r in _records(DF)],
                        value=None,
                        label=f"Breaks (pick one for details) — {len(DF)} spot(s)",
                        elem_classes=["break-list"],
                    )
                    fc_header = gr.Markdown(_NO_BREAK_HEADER)
                    fc_skill = gr.Dropdown(
                        SKILL_ORDER, value="intermediate", label="Skill level"
                    )
                    status_box = gr.Textbox(
                        label="Status",
                        interactive=False,
                        placeholder="Pick a break — forecast loads automatically…",
                    )
                    with gr.Tabs():
                        with gr.Tab("Score"):
                            score_plot = gr.Plot(label="Score (0-10)")
                        with gr.Tab("Swell"):
                            waves_plot = gr.Plot(label="Swell")
                        with gr.Tab("Wind"):
                            wind_plot = gr.Plot(label="Wind (kt)")
                    report_btn = gr.Button("Generate surf report ✨", variant="secondary")
                    report_md = gr.Markdown(_NO_REPORT_MD)
                    report_telemetry_box = gr.Textbox(
                        label="Report telemetry (tool calls)",
                        lines=8,
                        max_lines=14,
                        interactive=False,
                        placeholder="Pick a break for auto scoring trace, then “Generate surf report”…",
                    )
        with gr.Group(visible=False) as agent_group:
            gr.Markdown("### Agentic mode")
            gr.Markdown(
                "chat with the smolagents surf agent (`app/agent.py`) — it calls "
                "forecast/scoring tools and explains in the chat. "
                "charts + leaderboard appear below only when the agent "
                "actually scores a spot. pick a break in browse mode for "
                "context, or just name one in your question."
            )
            with gr.Row():
                pref_state = gr.Dropdown(
                    [ALL, *STATES], value=ALL, label="State preference"
                )
                pref_region = gr.Dropdown(
                    [ALL, *ALL_REGIONS], value=ALL, label="Region preference"
                )
                agent_skill = gr.Dropdown(
                    SKILL_ORDER,
                    value="intermediate",
                    label="Skill level",
                )
                stance_dd = gr.Dropdown(
                    ["natural", "goofy", "no preference"],
                    value="no preference",
                    label="Stance",
                )
                daypart_dd = gr.Dropdown(
                    ["all day", "mornings", "weekend"],
                    value="all day",
                    label="When",
                )
            pref_chip = gr.Markdown(
                "_Prefs: state=All · region=All · skill=intermediate · "
                "stance=no preference · viewing=none_"
            )
            with gr.Row():
                agent_token = gr.Textbox(
                    label="HF token (optional)",
                    type="password",
                    placeholder="Defaults to HF_TOKEN env — per-session override, never logged.",
                )
            with gr.Row():
                chip1 = gr.Button("Best in NSW this weekend (beginner)", variant="secondary")
                chip2 = gr.Button("Bells Beach mornings?", variant="secondary")
                chip3 = gr.Button("Quieter like Snapper?", variant="secondary")
                chip4 = gr.Button("Wetsuit + sunrise at Noosa?", variant="secondary")
            with gr.Group(elem_classes=["chat-panel"]):
                agent_chat = gr.Chatbot(label="Surf agent", height=420)
                with gr.Row(elem_classes=["chat-input-row"]):
                    agent_msg = gr.Textbox(
                        show_label=False,
                        value="What does the surf look like this morning?",
                        placeholder="e.g. When should I surf Bells Beach this week? (Enter to send)",
                        container=False,
                        scale=8,
                    )
                    agent_send = gr.Button("Send", variant="primary", scale=1)
                    agent_clear = gr.Button("Clear", variant="stop", scale=1)
            agent_telemetry_box = gr.Textbox(
                label="Agent activity (live tool calls)",
                lines=8,
                max_lines=14,
                interactive=False,
                placeholder="Send a question — tools start/finish here live, e.g. scoring Bells Beach…",
            )
            agent_status_box = gr.Textbox(
                label="Status",
                interactive=False,
                placeholder="Ask about a break — charts appear as each spot is scored…",
            )
            with gr.Group(visible=False) as agent_charts_group:
                agent_best_md = gr.Markdown("_No agent answer yet._")
                agent_spot_dd = gr.Dropdown(
                    choices=[],
                    value=None,
                    visible=False,
                    label="Chart spot (multiple scored)",
                )
                with gr.Tabs():
                    with gr.Tab("Score"):
                        agent_score_plot = gr.Plot(label="Score (0-10)")
                    with gr.Tab("Swell"):
                        agent_waves_plot = gr.Plot(label="Swell")
                    with gr.Tab("Wind"):
                        agent_wind_plot = gr.Plot(label="Wind (kt)")
            with gr.Group(visible=False) as agent_rank_group:
                agent_rank_df = gr.Dataframe(
                    headers=["Rank", "Spot", "Region", "Best score", "Best time"],
                    label="Leaderboard (rank_spots_this_week — click a row to ask about it)",
                    wrap=True,
                )

        def _toggle_custom_box(visible: bool):
            return gr.update(visible=not visible), not visible

        box_visible = gr.State(False)
        cant_find_btn.click(
            _toggle_custom_box,
            inputs=box_visible,
            outputs=[custom_box, box_visible],
        )
        custom_state_dd.change(
            update_custom_regions,
            inputs=custom_state_dd,
            outputs=custom_region_dd,
        )

        state_dd.change(
            update_region_choices, inputs=state_dd, outputs=region_dd
        ).then(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        )
        region_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        )
        skill_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df],
        )
        break_dd.change(
            on_break_pick,
            inputs=[break_dd, records_state, custom_state],
            outputs=[details_df, selected_break, fc_header, fc_skill, agent_skill, break_dd, fc_break_dd],
        ).then(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        )
        fc_break_dd.change(
            on_break_pick,
            inputs=[fc_break_dd, records_state, custom_state],
            outputs=[details_df, selected_break, fc_header, fc_skill, agent_skill, break_dd, fc_break_dd],
        ).then(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        )
        fc_skill.change(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        )
        mode_toggle.change(
            on_mode_change,
            inputs=mode_toggle,
            outputs=[browse_group, agent_group, intro_md],
        )
        go_forecast_btn.click(
            go_to_forecast,
            inputs=None,
            outputs=[tabs, mode_toggle, browse_group, agent_group, intro_md],
        )
        generate_btn.click(
            generate_custom_break,
            inputs=[
                custom_name_txt,
                custom_state_dd,
                custom_region_dd,
                records_state,
                custom_state,
                state_dd,
                region_dd,
            ],
            outputs=[telemetry_box, details_df, map_plot, break_dd, fc_break_dd, custom_state],
        )
        clear_btn.click(
            clear_custom_break,
            inputs=[records_state, selected_break],
            outputs=[
                custom_state,
                telemetry_box,
                details_df,
                map_plot,
                break_dd,
                fc_break_dd,
                selected_break,
                fc_header,
                fc_skill,
            ],
        )
        report_btn.click(
            generate_reports,
            inputs=[scored_state],
            outputs=[
                report_md,
                report_telemetry_box,
            ],
        )
        pref_state.change(
            update_region_choices, inputs=pref_state, outputs=pref_region
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        for _comp in (pref_region, agent_skill, stance_dd, daypart_dd):
            _comp.change(
                _format_pref_chip,
                inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
                outputs=pref_chip,
            )
        agent_send.click(
            chat_fn,
            inputs=[agent_msg, agent_chat, agent_skill, agent_token, selected_break, pref_state, pref_region, stance_dd, agent_skill, agent_session, agent_token_used, agent_conv, agent_charts, daypart_dd],
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        agent_msg.submit(
            chat_fn,
            inputs=[agent_msg, agent_chat, agent_skill, agent_token, selected_break, pref_state, pref_region, stance_dd, agent_skill, agent_session, agent_token_used, agent_conv, agent_charts, daypart_dd],
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        agent_spot_dd.change(
            on_agent_spot_change,
            inputs=[agent_spot_dd, agent_charts, selected_break],
            outputs=[
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
            ],
        )
        agent_clear.click(
            clear_agent_chat,
            inputs=None,
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        chip1.click(
            lambda: gr.update(value="Where should I surf in New South Wales this weekend as a beginner?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip2.click(
            lambda: gr.update(value="When are the best morning windows at Bells Beach this week?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip3.click(
            lambda: gr.update(value="What breaks are like Snapper Rocks but quieter?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip4.click(
            lambda: gr.update(value="What is the water temp + sunrise/sunset for Noosa Heads this week, and what wetsuit?"),
            inputs=None,
            outputs=agent_msg,
        )
        agent_rank_df.select(
            on_rank_select,
            inputs=agent_rank_df,
            outputs=agent_msg,
        )
    return demo


def main():
    build_demo().launch(css=APP_CSS, favicon_path=str(FAVICON_PATH))


if __name__ == "__main__":
    main()
