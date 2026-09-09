"""Intel rail: the world model + the when-to-go climatology.

Static panels — components only. Their inputs arrive through the shared
contracts: world-model figs come from the staged fetch (FETCH_KEYS),
climatology from the spot pick (SELECT_KEYS). Break details live in the
lens column, directly under the map.
"""

from __future__ import annotations

import gradio as gr


def build_intel():
    """Build the intel rail (inside an existing Column). Returns components."""
    with gr.Accordion("🌍 world model — gebco 2020", open=True):
        gr.Markdown("bathymetry around the takeoff zone (blue = deep, green = land, "
                    "★ = break). the 3D view carries an **animated swell layer** that "
                    "rides the forecast's dominant period — press ▶ swell.")
        surface_plot = gr.Plot(label="3D seafloor")
        seafloor_md = gr.Markdown("_resolves with the forecast — real GEBCO grid._")
        with gr.Accordion("depth + transects", open=False):
            depth_plot = gr.Plot(label="Depth map")
            transect_plot = gr.Plot(label="Transects")
    with gr.Accordion("📅 when to go — era5 5-yr climatology", open=True):
        year_plot = gr.Plot(label="When to go")
        months_md = gr.Markdown("_pick a spot — its climatology lands here._")
        rose_plot = gr.Plot(label="Swell climate rose")

    return {
        "surface_plot": surface_plot, "depth_plot": depth_plot,
        "transect_plot": transect_plot, "seafloor_md": seafloor_md,
        "year_plot": year_plot, "months_md": months_md, "rose_plot": rose_plot,
    }
