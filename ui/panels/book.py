"""Break-book panel: map + one-way filters + details + climate + audit.

One-way filters only (the v1 filter↔prefs two-way mirroring was cut per
plan). Handlers close over the catalogue records, so no session state is
needed here — the shared pick lives in the app-level selected state.
"""

from __future__ import annotations

import gradio as gr
import pandas as pd

from ui import _compat as C
from ui.charts import climate as climate_chart
from ui.charts import map as map_chart


def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def break_to_table(break_: dict) -> pd.DataFrame:
    """Flatten one break record into a Field/Value table (port of v1 details)."""
    loc = (break_ or {}).get("location", {}) or {}
    coords = loc.get("coordinates", {}) or {}
    swell = (break_ or {}).get("idealSwell", {}) or {}
    swell_size = swell.get("sizeRangeFt", {}) or {}
    wind = (break_ or {}).get("idealWind", {}) or {}
    tide = (break_ or {}).get("idealTide", {}) or {}
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


_EMPTY_DETAILS = pd.DataFrame(columns=["Field", "Value"])


def build_book(records: list[dict], vocab: dict, selected) -> dict:
    """Build the break-book tab. Returns component/handler dict for wiring."""
    states = vocab["states"]
    regions_by_state = vocab["regions_by_state"]
    all_regions = vocab["all_regions"]
    skills = vocab["skills"]
    names = [r.get("name", "?") for r in records]

    def state_regions(state: str) -> dict:
        regions = regions_by_state.get(state, all_regions) if state != C.ALL else all_regions
        return gr.update(choices=[C.ALL, *regions], value=C.ALL)

    def filter_changed(state: str, region: str, skill: str):
        """Re-filter, rebuild the map, refresh the break choices."""
        filtered = C.filter_records(records, state, region, skill)
        unfiltered = all(v in (None, C.ALL) for v in (state, region, skill))
        fig = map_chart.build_map(filtered, default_view=unfiltered)
        fnames = [r.get("name", "?") for r in filtered]
        picker = gr.update(choices=fnames, value=None,
                           label=f"Breaks (pick one for details) — {len(fnames)} spot(s)")
        return fig, picker

    def pick_changed(label: str | None):
        """Details + climate rose + audit chips for the picked break."""
        record = C.find_break(records, label)
        if record is None:
            return (_EMPTY_DETAILS, climate_chart.build_rose_fig(None),
                    "_Pick a break — its climate audit lands here._",
                    "### no break selected", None)
        header = f"### {record.get('name', '?')} — {record.get('region', '?')}, {record.get('state', '?')}"
        try:
            profile = C.get_climate_profile(record)
        except Exception:
            profile = {}
        try:
            findings = C.get_audit_findings(record)
        except Exception:
            findings = []
        return (break_to_table(record), climate_chart.build_rose_fig(profile, record.get("name", "")),
                climate_chart.format_findings(findings), header, record)

    with gr.Tab("break book"):
        gr.Markdown("### break book")
        gr.Markdown("filter spots, hover a dot for its name, then pick a break for details.")
        with gr.Row():
            state_dd = gr.Dropdown([C.ALL, *states], value=C.ALL, label="State")
            region_dd = gr.Dropdown([C.ALL, *all_regions], value=C.ALL, label="Region")
            skill_dd = gr.Dropdown([C.ALL, *skills], value=C.ALL, label="Skill level")
        with gr.Row():
            with gr.Column(scale=3):
                map_plot = gr.Plot(map_chart.build_map(records, default_view=True), label="Spots")
            with gr.Column(scale=2):
                break_radio = gr.Radio(
                    choices=names, value=None,
                    label=f"Breaks (pick one for details) — {len(names)} spot(s)",
                    elem_classes=["break-list"],
                )
                pick_header = gr.Markdown("### no break selected")
                details_df = gr.Dataframe(
                    headers=["Field", "Value"], label="Break details", wrap=True,
                )
        with gr.Row():
            with gr.Column(scale=1):
                rose_plot = gr.Plot(climate_chart.build_rose_fig(None), label="Swell climate rose")
            with gr.Column(scale=1):
                audit_md = gr.Markdown("_Pick a break — its climate audit lands here._")

    return {
        "state_dd": state_dd, "region_dd": region_dd, "skill_dd": skill_dd,
        "map_plot": map_plot, "break_radio": break_radio, "pick_header": pick_header,
        "details_df": details_df, "rose_plot": rose_plot, "audit_md": audit_md,
        "state_regions": state_regions, "filter_changed": filter_changed,
        "pick_changed": pick_changed,
    }
