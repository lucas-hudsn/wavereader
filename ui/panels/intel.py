"""Intel rail: three click-through tabs on the right edge of the page.

**surf report** (the LLM-narrated write-up, generated on demand),
**world model** (GEBCO bathymetry) and **when to go** (ERA5 climatology)
hang off one pill tab row — the header mode-toggle pattern: a Radio
swaps three stacked columns. (Gradio's native Tabs park overflow tabs in
a "⋯" menu at this column width; the rail keeps its own switcher
instead.) Components only — their inputs arrive through the shared
contracts: the report button wires in ``ui/app.py``, world-model figs
come from the staged fetch (FETCH_KEYS), climatology from the spot pick
(SELECT_KEYS).
"""

from __future__ import annotations

import gradio as gr

_TABS = ["report", "topography", "season"]


def build_intel():
    """Build the intel rail (inside an existing Column). Returns components."""
    tab_picker = gr.Radio(_TABS, value=_TABS[0], show_label=False,
                          container=False, elem_classes=["intel-tabs"])
    with gr.Column(visible=True) as report_col:
        narrate_btn = gr.Button("get surf report ✨", variant="secondary")
        report_md = gr.Markdown(
            "_no report yet — pick a spot, then get the surf report._")
    with gr.Column(visible=False) as world_col:
        gr.Markdown("bathymetry around the takeoff zone (blue = deep, green = land, "
                    "★ = break). the 3D view carries an **animated swell layer** that "
                    "rides the forecast's dominant period — press ▶ swell.")
        surface_plot = gr.Plot(label="3D seafloor")
        seafloor_md = gr.Markdown("_resolves with the forecast — real GEBCO grid._")
        with gr.Accordion("depth + transects", open=False):
            depth_plot = gr.Plot(label="Depth map")
            transect_plot = gr.Plot(label="Transects")
    with gr.Column(visible=False) as climate_col:
        year_plot = gr.Plot(label="When to go")
        months_md = gr.Markdown("_pick a spot — its climatology lands here._")
        rose_plot = gr.Plot(label="Swell climate rose")

    def pick(tab: str):
        """Tab switch: show the picked feature column, hide the others."""
        return (gr.update(visible=tab == _TABS[0]),
                gr.update(visible=tab == _TABS[1]),
                gr.update(visible=tab == _TABS[2]))

    return {
        "tab_picker": tab_picker, "pick": pick,
        "report_col": report_col, "world_col": world_col, "climate_col": climate_col,
        "narrate_btn": narrate_btn, "report_md": report_md,
        "surface_plot": surface_plot, "depth_plot": depth_plot,
        "transect_plot": transect_plot, "seafloor_md": seafloor_md,
        "year_plot": year_plot, "months_md": months_md, "rose_plot": rose_plot,
    }
