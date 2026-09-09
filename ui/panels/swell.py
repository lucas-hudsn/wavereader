"""Swell-check panel: staged deterministic forecast + world model + narrate.

``fetch_forecast`` is a *staged generator* so the spin-up reads as engines
working, not a spinner: stage 1 lands the Open-Meteo fetch + scored chart
trio immediately (~ms warm), while the GEBCO world model resolves in a
parallel thread and streams in as stage 2. Stage timings (feed, scorer,
world model) land in the status line — the LLM never owns the numbers.
"""

from __future__ import annotations

import threading
import time

import gradio as gr

from ui import _compat as C
from ui import _stubs as _stub
from ui.charts import score as score_chart
from ui.charts import seafloor as seafloor_chart
from ui.charts import swell as swell_chart
from ui.charts import wind as wind_chart

_SKILLS = _stub.SKILL_ORDER


def _loading_seafloor():
    load = seafloor_chart._loading_fig()
    return load, load, load


def _fmt_ms(ms: float) -> str:
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def _fail(msg: str):
    blank = score_chart._empty_fig()
    s_blank = seafloor_chart._empty_fig()
    return (msg, msg, "_No week summary yet._", blank, blank, blank,
            s_blank, s_blank, s_blank, "_No seafloor yet._", None)


def fetch_forecast(selected: dict | None, skill: str, progress=gr.Progress()):
    """Staged deterministic forecast: charts first, world model in parallel.

    Stage 1 (broadcast fast): Open-Meteo marine+wind → scoring engine →
    score/swell/wind charts + hero. Stage 2: the GEBCO seafloor thread
    joins → depth map + animated 3D surface (swell layer rides the
    forecast's dominant period) + transects. Every stage prints its engine
    and latency to the status line.
    """
    skill = (skill or "intermediate").strip().lower()
    if not selected:
        yield _fail("⚠️ Pick a break in the break book first.")
        return

    sea_holder: dict = {}
    sea_thread: threading.Thread | None = None

    def _sea_worker():
        t0 = time.perf_counter()
        try:
            sea = C.get_seafloor(selected)
            sea_holder.update(ok=True, sea=sea, ms=(time.perf_counter() - t0) * 1000)
        except Exception as e:  # noqa: BLE001 — surface the failure in status
            sea_holder.update(ok=False, err=str(e), ms=(time.perf_counter() - t0) * 1000)

    # World model starts fetching NOW, in parallel with the swell feed.
    sea_thread = threading.Thread(target=_sea_worker, daemon=True)
    sea_thread.start()

    t0 = time.perf_counter()
    try:
        progress(0.1, desc="📡 swell feed — Open-Meteo marine + wind…")
        payload = C.get_scored_week(selected, skill=skill, days=7)
    except (ValueError, RuntimeError) as e:
        yield _fail(f"❌ Forecast failed: {e}")
        return
    feed_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    scored = payload.get("scored", []) or []
    spot = payload.get("spot", {}) or {}
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
    score_ms = (time.perf_counter() - t1) * 1000
    best = payload.get("best") or {}

    full_payload = dict(payload, days=7)
    full_payload["break"] = selected
    header = f"### {selected.get('name', '?')} — {selected.get('region', '?')}, {selected.get('state', '?')}"
    base_status = (
        f"📡 Open-Meteo marine+wind — {_fmt_ms(feed_ms)} · "
        f"⚙ scoring engine — {len(scored)} hrs in {_fmt_ms(score_ms)} · "
        f"best {best.get('score')}/10 @ {best.get('time')}"
    )
    wetsuit = payload.get("wetsuit_hint")
    if wetsuit:
        base_status += f" · 🤿 {wetsuit}"
    loading = _loading_seafloor()
    yield (header, base_status + " · 🌍 world model: resolving GEBCO bathymetry…",
           hero, score_fig, swell_fig, wind_fig, *loading,
           "_🌍 world model — GEBCO 2020 grid resolving…_", full_payload)

    # -- stage 2: the world model --
    progress(0.85, desc="🌍 world model — GEBCO 2020 bathymetry…")
    if sea_thread is not None:
        sea_thread.join()
    if not sea_holder.get("ok"):
        err = sea_holder.get("err", "unavailable")
        status = base_status + f" · 🌍 world model unavailable ({err})"
        blank = seafloor_chart._empty_fig()
        yield (header, status, hero, score_fig, swell_fig, wind_fig,
               blank, blank, blank, f"_🌍 Seafloor unavailable: {err}_", full_payload)
        return
    sea = sea_holder["sea"]
    grid = sea.get("grid") or {}
    stats = sea.get("stats") or {}
    dataset = str(stats.get("dataset") or "2020").replace("gebco", "").strip() or "2020"
    wave = {
        "height_m": best.get("wave_height_m"),
        "period_s": best.get("wave_period_s"),
    }
    depth_fig = seafloor_chart.build_depth_fig(grid, selected.get("name", ""))
    surface_fig = seafloor_chart.build_surface_fig(grid, selected.get("name", ""), wave=wave)
    transect_fig = seafloor_chart.build_transect_fig(grid, selected.get("name", ""))
    sea_ms = sea_holder.get("ms", 0)
    sea_md = (
        f"🌍 **world model** — GEBCO {dataset} grid · "
        f"{stats.get('points', '?')} pts over a {stats.get('box_km', 2.4)} km box · "
        f"centre {stats.get('center_elev_m', '?')} m · relief {stats.get('relief_m', '?')} m · "
        f"{stats.get('shelf_class', '?')} · resolved in {_fmt_ms(sea_ms)}\n\n"
        + (sea.get("analysis") or "")
    )
    status = base_status + f" · 🌍 GEBCO world model — {_fmt_ms(sea_ms)} · 3D + transects ready"
    progress(1.0, desc="✅ forecast + world model ready")
    yield (header, status, hero, score_fig, swell_fig, wind_fig,
           depth_fig, surface_fig, transect_fig, sea_md, full_payload)


def narrate(payload: dict | None):
    """Stream the surf-report markdown; the LLM's engine is named first."""
    yield "_🧠 llm — **Nemotron 3.5 Lightning** (fireworks-ai via Inference Providers) streaming…_"
    yield from C.narrate_stream(payload)


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
                gr.Markdown("🌍 **world model** — GEBCO 2020 bathymetry around the takeoff zone "
                            "(blue = deep, green = land, ★ = break). The 3D view carries an "
                            "**animated swell layer** at the forecast's dominant period — press ▶ swell.")
                depth_plot = gr.Plot(label="Depth map")
                surface_plot = gr.Plot(label="3D seafloor")
                transect_plot = gr.Plot(label="Transects")
                seafloor_md = gr.Markdown("_🌍 world model loads with the forecast — GEBCO bathymetry, 3D + transects._")
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
