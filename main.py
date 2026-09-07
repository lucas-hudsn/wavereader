"""Gradio map front end for Australian surf breaks."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import gradio as gr
import pandas as pd
from plotly import graph_objects as go

DATA_PATH = Path(__file__).parent / "data" / "australia-surf-breaks-enriched.json"
GENERATOR_PATH = Path(__file__).parent / "app" / "generate_surf_break.py"
FORECAST_PATH = Path(__file__).parent / "app" / "surf_forecast.py"

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
/* wave~reader lo-fi theme: light blue bg, dark blue font */
.gradio-container, .gradio-container-4x, main, body {
    background: #d6e9f8 !important;
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
.hero-sub {
    font-size: 1.3em !important;
    text-transform: uppercase;
    letter-spacing: 3px;
    border-top: 2px dashed #0b2c5c;
    border-bottom: 2px dashed #0b2c5c;
    padding: 6px 0;
}
button, select {
    font-family: "Courier New", Courier, monospace !important;
}
.break-list { max-height: 210px; overflow-y: auto; border: 1px solid #0b2c5c; border-radius: 8px; padding: 4px; background: #eef6fd !important; }
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


def _empty_forecast_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No forecast data", showarrow=False, font={"size": 16})
    return fig


_NO_BREAK_HEADER = "### No break selected — pick one in the encyclopedia tab."


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
    colors = [SKILL_COLORS.get(s.lower(), "#1f77b4") for s in skills]

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
        fig.add_trace(
            go.Scattermap(
                lat=lats,
                lon=lngs,
                mode="markers",
                marker={"size": 10, "color": colors},
                text=names,
                customdata=list(zip(names, regions, skills)),
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>"
                    "%{customdata[1]} · %{customdata[2]}"
                    "<extra></extra>"
                ),
            )
        )
    fig.update_layout(
        map_style="open-street-map",
        hovermode="closest",
        height=550,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        map=dict(center={"lat": center_lat, "lon": center_lng}, zoom=zoom),
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


def _resolve_pick(break_label: str, base_records: list[dict], custom: dict | None) -> dict | None:
    """Map a Break-list label back to its record (custom break has a ⭐ suffix)."""
    if custom and break_label == f"{custom.get('name', '')} ⭐ (your break)":
        return custom
    for r in base_records:
        if r.get("name") == break_label:
            return r
    return None


def update_map(state: str, region: str, skill: str, custom: dict | None):
    """Re-filter, rebuild the map (with custom highlight), refresh break choices."""
    df = filter_breaks(DF, state, region, skill)
    records = _records(df)
    unfiltered = all(v in (None, ALL) for v in (state, region, skill))
    fig = build_map_with_custom(records, custom, default_view=unfiltered)
    names = _effective_names(records, custom)
    count = f"**{len(records)}** spot(s)"
    if custom:
        count += " + **1** your break ⭐"
    return (
        fig,
        gr.update(choices=names, value=None),
        records,
        count,
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
    """Update details + shared forecast state when the break list changes.

    Also refreshes the forecast-tab header and the forecast skill default
    (the break's own skillLevel). Works for base records and the custom ⭐
    break via ``_resolve_pick``.
    """
    empty_details = pd.DataFrame(columns=["Field", "Value"])
    if not break_label:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip()
    record = _resolve_pick(break_label, records or [], custom)
    if record is None:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip()
    raw_skill = str(record.get("skillLevel") or "intermediate").strip().lower()
    skill_value = raw_skill if raw_skill in SKILL_ORDER else "intermediate"
    header = (
        f"### {record.get('name', '?')} — "
        f"{record.get('region', '?')}, {record.get('state', '?')}"
    )
    return (
        break_to_table(record),
        record,
        header,
        gr.update(value=skill_value),
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
        yield (
            _telemetry(logs),
            details,
            fig,
            gr.update(choices=names, value=f"{custom.get('name', '')} ⭐ (your break)"),
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
    return (
        None,
        "🗑️ Session break deleted.",
        pd.DataFrame(columns=["Field", "Value"]),
        fig,
        gr.update(choices=names, value=None),
        None if was_selected_custom else gr.skip(),
        _NO_BREAK_HEADER if was_selected_custom else gr.skip(),
        gr.skip(),
    )


def fetch_forecast(
    selected_break: dict | None,
    skill: str,
    days: int,
    progress=gr.Progress(),
):
    """Score a 1–7 day forecast for the shared ``selected_break`` (explicit button).

    Deterministic only: delegates to ``app/surf_forecast.get_scored_week``
    (Open-Meteo + deterministic scoring; stale-cache fallback lives inside
    ``get_forecast``). No agent involved.
    """
    empty_df = pd.DataFrame()
    if not selected_break:
        return (
            "⚠️ Pick a break in the encyclopedia tab first.",
            "_Pick a break first._",
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            empty_df,
            empty_df,
        )
    try:
        try:
            days_int = max(1, min(7, int(days)))
        except (TypeError, ValueError):
            days_int = 7
        progress(0.1, desc="Loading forecast module…")
        mod = _load_forecast()
        progress(0.3, desc="Fetching + scoring forecast…")
        result = mod.get_scored_week(
            selected_break, skill=skill, days=days_int
        )
        scored = result.get("scored", []) or []
        progress(0.7, desc="Building charts…")
        score_fig = mod.build_score_fig(scored)
        waves_fig = mod.build_waves_fig(scored)
        wind_fig = mod.build_wind_fig(scored)
        best = mod.best_window(scored)
        if best:
            best_md = (
                f"**{best.get('score')}/10 @ {best.get('time')}** — "
                f"{best.get('wave_height_m')}m @ {best.get('wave_period_s')}s, "
                f"wind {best.get('wind_speed_kt')}kt "
                f"({best.get('wind_direction_deg')}°)"
            )
        else:
            best_md = "_No scored hours in this window._"
        daily = pd.DataFrame(mod.daily_best(scored))
        hourly_rows = []
        for r in scored:
            comps = r.get("components") or {}
            hourly_rows.append(
                {
                    "time": r.get("time"),
                    "score": r.get("score"),
                    "swell_size": comps.get("swell_size"),
                    "swell_direction": comps.get("swell_direction"),
                    "wind": comps.get("wind"),
                    "period": comps.get("period"),
                    "wave_height_m": r.get("wave_height_m"),
                    "wave_period_s": r.get("wave_period_s"),
                    "wind_speed_kt": r.get("wind_speed_kt"),
                }
            )
        hourly = pd.DataFrame(
            hourly_rows,
            columns=[
                "time",
                "score",
                "swell_size",
                "swell_direction",
                "wind",
                "period",
                "wave_height_m",
                "wave_period_s",
                "wind_speed_kt",
            ],
        )
        progress(1.0, desc="Done")
        status = (
            f"✅ {selected_break.get('name', '?')} · "
            f"skill {result.get('skill')} · "
            f"{len(scored)} hour(s) scored ({days_int}d)."
        )
        return (
            status,
            best_md,
            score_fig,
            waves_fig,
            wind_fig,
            daily,
            hourly,
        )
    except Exception as e:  # noqa: BLE001 — surface fetch/score errors in the status box
        return (
            f"❌ Forecast failed: {e}",
            "_Forecast failed._",
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            _empty_forecast_fig(),
            empty_df,
            empty_df,
        )


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="wave~reader — Australian surf encyclopaedia") as demo:
        gr.Markdown("# wave~reader", elem_classes=["hero-title"])
        gr.Markdown("## Australian surf encyclopaedia", elem_classes=["hero-sub"])
        gr.Markdown("filter spots, hover a dot for its name, then pick a break for details. [lo-fi edition]")
        records_state = gr.State(_records(DF))
        custom_state = gr.State(None)  # one session-only break; never persisted
        selected_break = gr.State(None)  # shared pick for the forecast tab
        with gr.Tab("encyclopedia"):
            with gr.Row():
                state_dd = gr.Dropdown([ALL, *STATES], value=ALL, label="State")
                region_dd = gr.Dropdown([ALL, *ALL_REGIONS], value=ALL, label="Region")
                skill_dd = gr.Dropdown([ALL, *SKILLS], value=ALL, label="Skill level")
            count_md = gr.Markdown(f"**{len(DF)}** spot(s)")
            with gr.Row():
                with gr.Column(scale=3):
                    map_plot = gr.Plot(build_map(_records(DF), default_view=True), label="Spots")
                    cant_find_btn = gr.Button(
                        "Can't find your local break?", variant="secondary"
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
                        label="Breaks (pick one for details)",
                        elem_classes=["break-list"],
                    )
                    details_df = gr.Dataframe(
                        headers=["Field", "Value"],
                        row_count=(16, "fixed"),
                        column_count=(2, "fixed"),
                        label="Break details",
                        wrap=True,
                    )
        with gr.Tab("surf forecast"):
            fc_header = gr.Markdown(_NO_BREAK_HEADER)
            with gr.Row():
                fc_skill = gr.Dropdown(
                    SKILL_ORDER, value="intermediate", label="Skill level"
                )
                days_slider = gr.Slider(1, 7, value=7, step=1, label="Days")
            fetch_btn = gr.Button("Get forecast", variant="primary")
            status_box = gr.Textbox(
                label="Status",
                interactive=False,
                placeholder="Pick a break, then press “Get forecast”…",
            )
            best_md = gr.Markdown("_No forecast yet._")
            score_plot = gr.Plot(label="Score")
            waves_plot = gr.Plot(label="Swell")
            wind_plot = gr.Plot(label="Wind")
            daily_df = gr.Dataframe(label="Best hour each day", wrap=True)
            hourly_df = gr.Dataframe(label="All scored hours", wrap=True)

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
            outputs=[map_plot, break_dd, records_state, count_md, details_df],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        )
        region_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, records_state, count_md, details_df],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        )
        skill_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, records_state, count_md, details_df],
        )
        break_dd.change(
            on_break_pick,
            inputs=[break_dd, records_state, custom_state],
            outputs=[details_df, selected_break, fc_header, fc_skill],
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
            outputs=[telemetry_box, details_df, map_plot, break_dd, custom_state],
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
                selected_break,
                fc_header,
                fc_skill,
            ],
        )
        fetch_btn.click(
            fetch_forecast,
            inputs=[selected_break, fc_skill, days_slider],
            outputs=[
                status_box,
                best_md,
                score_plot,
                waves_plot,
                wind_plot,
                daily_df,
                hourly_df,
            ],
        )
    return demo


def main():
    build_demo().launch(css=APP_CSS)


if __name__ == "__main__":
    main()
