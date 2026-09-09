"""Swell-check panel: score/swell/wind/seafloor tabs + p75 hero + narrate.

Stage 1 (``fetch_forecast``) is deterministic — charts render from the typed
scored payload immediately. Stage 2 (``narrate``) streams markdown prose
over those numbers; the LLM never owns the numbers.
"""

from __future__ import annotations

import gradio as gr

from ui import _compat as C
from ui import _stubs as _stub
from ui.charts import score as score_chart
from ui.charts import seafloor as seafloor_chart
from ui.charts import swell as swell_chart
from ui.charts import wind as wind_chart

_SKILLS = _stub.SKILL_ORDER


def _blank_seafloor(name: str = ""):
    blank = seafloor_chart._empty_fig()
    return blank, blank, blank, f"_{name}_" if name else "_Pick a break — its seafloor model loads automatically._"


def fetch_forecast(selected: dict | None, skill: str):
    """Deterministic forecast: score + build chart trio + seafloor + hero."""
    skill = (skill or "intermediate").strip().lower()
    if not selected:
        msg = "⚠️ Pick a break in the break book first."
        blank = score_chart._empty_fig()
        s_blank, *_ = _blank_seafloor()
        return (msg, msg, "_No week summary yet._", blank, blank, blank,
                s_blank, s_blank, s_blank, "_No seafloor yet._", None)
    try:
        payload = C.get_scored_week(selected, skill=skill, days=7)
    except (ValueError, RuntimeError) as e:
        msg = f"❌ Forecast failed: {e}"
        blank = score_chart._empty_fig()
        s_blank, *_ = _blank_seafloor()
        return (msg, msg, "_No week summary yet._", blank, blank, blank,
                s_blank, s_blank, s_blank, "_No seafloor yet._", None)
    scored = payload.get("scored", []) or []
    spot = payload.get("spot", {}) or {}
    skill_used = payload.get("skill", skill)
    score_fig = score_chart.build_score_fig(scored)
    swell_fig = swell_chart.build_waves_fig(scored)
    wind_fig = wind_chart.build_wind_fig(scored, spot)
    try:
        score_fig = score_chart.add_sun_markers(score_fig, payload.get("sun"))
        swell_fig = score_chart.add_sun_markers(swell_fig, payload.get("sun"))
    except (AttributeError, TypeError, ValueError):
        pass
    summary = score_chart.daily_summary(scored)
    hero = score_chart.format_hero(summary, selected.get("name", "?"))
    best = payload.get("best") or {}
    status = (f"✅ {selected.get('name', '?')} · skill {skill_used} · "
              f"{len(scored)} hour(s) scored. Best {best.get('score')}/10 @ {best.get('time')}.")
    wetsuit = payload.get("wetsuit_hint")
    if wetsuit:
        status += f" 🤿 {wetsuit}."
    header = f"### {selected.get('name', '?')} — {selected.get('region', '?')}, {selected.get('state', '?')}"
    full_payload = dict(payload, days=7)
    full_payload["break"] = selected
    try:
        sea = C.get_seafloor(selected)
        grid = sea.get("grid") or {}
        name = selected.get("name", "")
        depth_fig = seafloor_chart.build_depth_fig(grid, name)
        surface_fig = seafloor_chart.build_surface_fig(grid, name)
        transect_fig = seafloor_chart.build_transect_fig(grid, name)
        sea_md = sea.get("analysis") or "_Seafloor grid loaded._"
    except (ValueError, RuntimeError) as e:
        depth_fig = seafloor_chart._empty_fig()
        surface_fig = seafloor_chart._empty_fig()
        transect_fig = seafloor_chart._empty_fig()
        sea_md = f"_Seafloor unavailable: {e}_"
    return (header, status, hero, score_fig, swell_fig, wind_fig,
            depth_fig, surface_fig, transect_fig, sea_md, full_payload)


def narrate(payload: dict | None):
    """Stream the surf-report markdown for a scored payload."""
    for chunk in C.narrate_stream(payload):
        yield chunk


def build_swell(selected, scored) -> dict:
    """Build the swell-check tab. Returns component dict for wiring."""
    with gr.Tab("swell check"):
        gr.Markdown("### swell check")
        gr.Markdown("charts load automatically from the break-book pick + an optional ai report.")
        header_md = gr.Markdown("### no break selected — pick one in the break book tab.")
        with gr.Row():
            skill_dd = gr.Dropdown(_SKILLS, value="intermediate", label="Skill level")
        status_box = gr.Textbox(label="Status", interactive=False,
                                placeholder="Pick a break — forecast loads automatically…")
        hero_md = gr.Markdown("_No week summary yet._")
        with gr.Tabs():
            with gr.Tab("Score"):
                score_plot = gr.Plot(label="Score (0-10)")
                with gr.Accordion("how the score is calculated", open=False):
                    gr.Markdown("**0–10 = 30% size · 20% direction · 30% wind · 20% period**\n\n"
                                "red→green bars; ★ = best hour; daily hero ranks by p75 consistency.")
            with gr.Tab("Swell"):
                swell_plot = gr.Plot(label="Swell")
            with gr.Tab("Wind"):
                wind_plot = gr.Plot(label="Wind (kt)")
            with gr.Tab("Seafloor"):
                gr.Markdown("world model — bathymetry around the takeoff zone "
                            "(blue = deep, green = land, ★ = break).")
                depth_plot = gr.Plot(label="Depth map")
                surface_plot = gr.Plot(label="3D seafloor")
                transect_plot = gr.Plot(label="Transects")
                seafloor_md = gr.Markdown("_Pick a break — its seafloor model loads automatically._")
        narrate_btn = gr.Button("Narrate the week ✨", variant="secondary")
        report_md = gr.Markdown("_No report yet — pick a break, then narrate the week._")

    return {
        "header_md": header_md, "skill_dd": skill_dd, "status_box": status_box,
        "hero_md": hero_md, "score_plot": score_plot, "swell_plot": swell_plot,
        "wind_plot": wind_plot, "depth_plot": depth_plot, "surface_plot": surface_plot,
        "transect_plot": transect_plot, "seafloor_md": seafloor_md,
        "narrate_btn": narrate_btn, "report_md": report_md,
        "fetch_forecast": fetch_forecast, "narrate": narrate,
    }
