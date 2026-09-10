"""Story panel: the selected spot's week — chips, strip, report.

``fetch_forecast`` stays a *staged generator* so the spin-up reads as
engines working, not a spinner: stage 1 lands the Open-Meteo fetch +
week strip immediately (~ms warm), while the GEBCO world model resolves
in a parallel thread and streams in as stage 2. Stage timings (feed,
scorer, world model) land in the status line — the LLM never owns the
numbers.
"""

from __future__ import annotations

import html
import threading
import time

import gradio as gr

from ui import _compat as C
from ui.charts import score as score_chart
from ui.charts import seafloor as seafloor_chart
from ui.charts import strip as strip_chart
from ui.contracts import FETCH_KEYS, fill


def _fmt_ms(ms: float) -> str:
    return f"{ms:.0f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def _join(value) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def format_badges(record: dict | None, cam: dict | None = None) -> str:
    """Spot identity as lo-fi chips: skill, type, tide, crowd, hazards, cam."""
    b = record or {}
    if not b:
        return ""
    esc = html.escape
    parts: list[str] = []
    skill = str(b.get("skillLevel", "")).lower()
    parts.append(f'<span class="badge-chip badge-skill badge-skill-{esc(skill or "?")}">'
                 f"🏄 {esc(str(b.get('skillLevel', '?')))}</span>")
    for label, key in (("type", "breakType"), ("peak", "peakType")):
        if b.get(key):
            parts.append(f'<span class="badge-chip">{label}: {esc(str(b[key]))}</span>')
    tide = _join((b.get("idealTide") or {}).get("stage"))
    if tide:
        parts.append(f'<span class="badge-chip">🌊 tide: {esc(tide)}</span>')
    swell = (b.get("idealSwell") or {}).get("sizeRangeFt") or {}
    if swell.get("min") is not None:
        parts.append(f'<span class="badge-chip">📏 likes {swell.get("min", "?")}–'
                     f'{swell.get("max", "?")} ft</span>')
    if b.get("crowdFactor"):
        parts.append(f'<span class="badge-chip">👥 {esc(str(b["crowdFactor"]))}</span>')
    if b.get("bestSeason"):
        parts.append(f'<span class="badge-chip">🗓 {esc(_join(b.get("bestSeason")))}</span>')
    for hz in (b.get("hazards") or []):
        parts.append(f'<span class="badge-chip badge-warn">⚠️ {esc(str(hz))}</span>')
    if cam and cam.get("url"):
        label = esc(str(cam.get("label") or "surf cam"))
        parts.append(f'<a class="badge-chip badge-link" href="{esc(str(cam["url"]))}" '
                     f'target="_blank" rel="noopener">📹 {label}</a>')
    return '<div class="badge-row">' + " ".join(parts) + "</div>"


def _empty_seafloor():
    blank = seafloor_chart._empty_fig()
    return blank, blank, blank


def _fail(msg: str):
    blank = score_chart._empty_fig()
    s_blank, s_blank2, s_blank3 = _empty_seafloor()
    return fill(FETCH_KEYS, status_box=msg,
                hero_md="_No week summary yet._",
                score_plot=blank, swell_plot=blank, wind_plot=blank,
                surface_plot=s_blank, depth_plot=s_blank2, transect_plot=s_blank3,
                seafloor_md="_No seafloor yet._", scored=None)


def fetch_forecast(selected: dict | None, skill: str, progress=gr.Progress()):
    """Staged deterministic forecast: strip first, world model in parallel.

    Stage 1 (broadcast fast): Open-Meteo marine+wind → scoring engine →
    week strip + day-chip hero. Stage 2: the GEBCO seafloor thread joins
    → 3D surface (the animated swell layer rides the forecast's dominant
    period) + depth map + transects. Every stage prints its engine and
    latency to the status line.
    """
    skill = C.scoring_skill(skill)
    if not selected:
        yield _fail("⚠️ Pick a spot — search above or filter the map.")
        return

    sea_holder: dict = {}

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
    score_fig, swell_fig, wind_fig = strip_chart.build_tabbed_figs(scored, spot)
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
    loading = seafloor_chart._loading_fig()
    yield fill(FETCH_KEYS, status_box=base_status + " · 🌍 world model: resolving GEBCO bathymetry…",
               hero_md=hero, score_plot=score_fig, swell_plot=swell_fig,
               wind_plot=wind_fig,
               surface_plot=loading, depth_plot=loading, transect_plot=loading,
               seafloor_md="_🌍 world model — GEBCO 2020 grid resolving…_", scored=full_payload)

    # -- stage 2: the world model --
    progress(0.85, desc="🌍 world model — GEBCO 2020 bathymetry…")
    sea_thread.join()
    if not sea_holder.get("ok"):
        err = sea_holder.get("err", "unavailable")
        status = base_status + f" · 🌍 world model unavailable ({err})"
        s_blank, s_blank2, s_blank3 = _empty_seafloor()
        yield fill(FETCH_KEYS, status_box=status, hero_md=hero,
                   score_plot=score_fig, swell_plot=swell_fig, wind_plot=wind_fig,
                   surface_plot=s_blank, depth_plot=s_blank2, transect_plot=s_blank3,
                   seafloor_md=f"_🌍 Seafloor unavailable: {err}_", scored=full_payload)
        return
    sea = sea_holder["sea"]
    grid = sea.get("grid") or {}
    stats = sea.get("stats") or {}
    dataset = str(stats.get("dataset") or "2020").replace("gebco", "").strip() or "2020"
    wave = {
        "height_m": best.get("wave_height_m"),
        "period_s": best.get("wave_period_s"),
        "direction_deg": best.get("wave_direction_deg"),
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
    yield fill(FETCH_KEYS, status_box=status, hero_md=hero,
               score_plot=score_fig, swell_plot=swell_fig, wind_plot=wind_fig,
               surface_plot=surface_fig, depth_plot=depth_fig, transect_plot=transect_fig,
               seafloor_md=sea_md, scored=full_payload)


def narrate(payload: dict | None):
    """Stream the surf-report markdown; the LLM's engine is named first."""
    try:
        from wavereader import llm as _l

        engine = f"**{_l.get_model_id().split('/')[-1]}** ({_l.get_provider()} via Inference Providers)"
    except ImportError:
        engine = "**Nemotron 3 Ultra** (deepinfra via Inference Providers)"
    yield f"_🧠 llm — {engine} streaming…_"
    yield from C.narrate_stream(payload)


def build_story(selected, scored):
    """Build the story column. Returns component dict for wiring."""
    with gr.Column(scale=4):
        spot_header = gr.Markdown("### pick a spot — search above or filter the map")
        badges_md = gr.Markdown()
        status_box = gr.Textbox(label="engines", interactive=False,
                                placeholder="the spin-up line — feed, scorer, world model — lands here…")
        hero_md = gr.Markdown("_the week summary lands here._")
        with gr.Tabs():
            with gr.Tab("score"):
                score_plot = gr.Plot(label="score — 0–10 by hour")
            with gr.Tab("swell"):
                swell_plot = gr.Plot(label="swell — height + period")
            with gr.Tab("wind"):
                wind_plot = gr.Plot(label="wind — speed + direction")
        gr.Markdown(f"<div class='strip-caption'>{strip_chart.CAPTION}</div>")
        narrate_btn = gr.Button("get surf report ✨", variant="secondary")
        report_md = gr.Markdown("_no report yet — pick a spot, then get the surf report._")

    return {
        "spot_header": spot_header, "badges_md": badges_md, "status_box": status_box,
        "hero_md": hero_md, "score_plot": score_plot, "swell_plot": swell_plot,
        "wind_plot": wind_plot,
        "narrate_btn": narrate_btn, "report_md": report_md,
        "fetch_forecast": fetch_forecast, "narrate": narrate,
    }
