"""Lens panel: search + one-way filters + the map (the app's entry point).

The map is the browse surface: hover a dot for the name, pick via the
searchable dropdown (Gradio 6 Plots expose no click event). Picking a
spot re-tells the whole page — story, intel, and agent context all hang
off the shared ``selected`` state. Handlers close over the catalogue
records, so no extra session state is needed here.
"""

from __future__ import annotations

import pandas as pd

import gradio as gr

from ui import _compat as C
from ui.charts import climate as climate_chart
from ui.charts import map as map_chart
from ui.contracts import SELECT_KEYS, fill


def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def break_to_table(break_: dict) -> pd.DataFrame:
    """Flatten one break record into a Field/Value table."""
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


def build_lens(records: list[dict], vocab: dict, selected):
    """Build the lens column. Returns component/handler dict for wiring."""
    states = vocab["states"]
    regions_by_state = vocab["regions_by_state"]
    all_regions = vocab["all_regions"]
    skills = vocab["skills"]
    names = [r.get("name", "?") for r in records]

    with gr.Column(scale=3, elem_classes=["lens-col"]):
        with gr.Row():
            state_dd = gr.Dropdown([C.ALL, *states], value=C.ALL, label="State",
                                   min_width=100)
            region_dd = gr.Dropdown([C.ALL, *all_regions], value=C.ALL, label="Region",
                                    min_width=100)
            skill_dd = gr.Dropdown([C.ALL, *skills], value=C.ALL, label="Skill",
                                    min_width=100)
        search_dd = gr.Dropdown(
            choices=names, value=None, label="pick a spot — type to search all 238",
            info="picking re-aims the whole page: story, world model, agent",
        )
        map_plot = gr.Plot(map_chart.build_map(records, default_view=True))
        gr.HTML(map_chart.skill_legend_html())
        with gr.Accordion("📖 break details", open=False):
            details_df = gr.Dataframe(headers=["Field", "Value"], wrap=True)

    def state_regions(state: str) -> dict:
        regions = regions_by_state.get(state, all_regions) if state != C.ALL else all_regions
        return gr.update(choices=[C.ALL, *regions], value=C.ALL)

    def filter_changed(state: str, region: str, skill: str):
        """Re-filter, rebuild the map (reframed on the matches), refresh choices."""
        filtered = C.filter_records(records, state, region, skill)
        unfiltered = all(v in (None, C.ALL) for v in (state, region, skill))
        fig = map_chart.build_map(filtered, default_view=unfiltered)
        fnames = [r.get("name", "?") for r in filtered]
        picker = gr.update(choices=fnames, value=None,
                           label=f"pick a spot — {len(fnames)} match the filters")
        return fig, picker

    def select_spot(record: dict | None, filtered: list[dict] | None = None,
                    fly: bool = True):
        """The one spot-pick pipeline: static story + intel for ``record``."""
        if record is None:
            return fill(SELECT_KEYS, selected=None)
        name = record.get("name", "?")
        header = f"### {name} — {record.get('region', '?')}, {record.get('state', '?')}"
        try:
            profile = C.get_climate_profile(record)
        except Exception:
            profile = {}
        if profile.get("source") != "era5-5yr":
            profile = {}  # the stub rose would be fabricated data — stay honest
        monthly = C.get_climate_monthly(record)
        cam = C.get_surf_cam(record)
        from ui.panels.story import format_badges

        fly_fig = (map_chart.build_map(filtered or [record], selected=record)
                   if fly else gr.skip())
        return fill(
            SELECT_KEYS,
            search_dd=record.get("name"),
            map_plot=fly_fig,
            spot_header=header,
            badges_md=format_badges(record, cam),
            rose_plot=climate_chart.build_rose_fig(
                profile, name,
                ideal_dirs=(record.get("idealSwell") or {}).get("direction"),
            ),
            year_plot=climate_chart.build_year_fig(
                monthly, name, window_label=profile.get("window_ft", ""),
            ),
            months_md=C.format_month_hint(monthly, profile),
            details_df=break_to_table(record),
            selected=record,
        )

    def pick_by_name(name: str | None, state: str, region: str, skill: str):
        """Search-dropdown pick → resolve → select_spot (map flies to it)."""
        record = C.find_break(records, name)
        if record is None:
            return fill(SELECT_KEYS, selected=None)
        filtered = C.filter_records(records, state, region, skill)
        return select_spot(record, filtered, fly=True)

    return {
        "search_dd": search_dd, "state_dd": state_dd, "region_dd": region_dd,
        "skill_dd": skill_dd, "map_plot": map_plot, "details_df": details_df,
        "state_regions": state_regions, "filter_changed": filter_changed,
        "pick_by_name": pick_by_name, "select_spot": select_spot,
    }
