"""Swell-check seafloor handler: deterministic bathymetry charts + analysis."""

from __future__ import annotations

import time

import gradio as gr
from plotly import graph_objects as go

from legacy.app.adapters import get_coords
from legacy.app.custom_break import _telemetry

_NO_SEAFLOOR_MD = "_Pick a break — its seafloor model loads automatically._"
_NO_EXPLAIN_MD = "_Press “Explain seafloor ✨” for a plain-language read (free-tier model)._"

_EXPLAIN_TELEMETRY_HINT = "explanation box below"


def _empty_seafloor_fig(text: str = "No seafloor data") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, showarrow=False, font={"size": 16})
    return fig


def fetch_seafloor(
    selected_break: dict | None,
    radius_km: float = 1.2,
    progress=gr.Progress(),
):
    """Stage-0 bathymetry: GEBCO grid → depth map + 3D surface + transects.

    Runs automatically on break pick (like ``fetch_forecast``) plus on
    radius change / manual refresh. Yields (status, depth_fig, surface_fig,
    transect_fig, analysis_md, telemetry, explanation_md) tuples.
    Deterministic — no LLM. The explanation box is always reset so a stale
    free-tier write-up never lingers after a new fetch.
    """
    logs: list[str] = []

    def emit(status, depth_fig, surface_fig, transect_fig, analysis_md):
        return (status, depth_fig, surface_fig, transect_fig, analysis_md, _telemetry(logs), _NO_EXPLAIN_MD)

    empty = (_empty_seafloor_fig(), _empty_seafloor_fig(), _empty_seafloor_fig())
    if not selected_break:
        logs.append("⚠️ No break selected — pick one in the break list above.")
        yield emit("⚠️ Pick a break first.", *empty, _NO_SEAFLOOR_MD)
        return
    lat, lng = get_coords(selected_break)
    if lat is None or lng is None:
        logs.append(f"⚠️ No coordinates for {selected_break.get('name', '?')}.")
        yield emit("⚠️ Break has no coordinates.", *empty, _NO_SEAFLOOR_MD)
        return
    try:
        radius = max(0.3, min(5.0, float(radius_km or 1.2)))
    except (TypeError, ValueError):
        radius = 1.2
    try:
        t0 = time.time()
        name = selected_break.get("name", "?")
        logs.append(
            f"🔧 [tool: get_seafloor] break='{name}' "
            f"lat={lat:.4f} lng={lng:.4f} radius={radius:.1f}km (OpenTopoData gebco2020 → analyze_grid)."
        )
        progress(0.2, desc="Fetching seafloor grid…")
        yield emit("⏳ Fetching seafloor grid…", *empty, "_Loading seafloor model…_")

        from legacy.app import seafloor as mod

        progress(0.5, desc="Analyzing shape…")
        res = mod.get_seafloor(lat, lng, radius_km=radius)
        grid, analysis_md, stats = res["grid"], res["analysis"], res["stats"]
        progress(0.8, desc="Building 3D view…")
        depth_fig = mod.build_depth_fig(grid, name)
        surface_fig = mod.build_surface_fig(grid, name)
        transect_fig = mod.build_transect_fig(grid, name)
        dt = time.time() - t0
        logs.append(
            f"📊 [tool: analyze_grid] {stats.get('points', '?')} pts "
            f"({stats.get('dataset', '?')}) → {stats.get('shelf_class', '?')} "
            f"in {dt:.1f}s."
        )
        status = (
            f"✅ {name} seafloor · {stats.get('dataset', '?')} · "
            f"{stats.get('box_km', '?')} km box · deepest {stats.get('max_depth_m', '?')} m · "
            f"{stats.get('shelf_class', '?')}."
        )
        progress(1.0, desc="Seafloor ready")
        yield emit(status, depth_fig, surface_fig, transect_fig, analysis_md)
    except Exception as e:  # noqa: BLE001 — surface fetch errors in the status box
        logs.append(f"❌ Seafloor failed: {e}")
        yield emit(f"❌ Seafloor failed: {e}", *empty, "_Seafloor load failed — retry below._")


def generate_seafloor_explanation(
    selected_break: dict | None,
    radius_km: float = 1.2,
    progress=gr.Progress(),
):
    """Stage-2 seafloor narrator on the HF free tier (opt-in button).

    Re-reads the cached GEBCO grid (no new bathymetry fetch in practice)
    and streams a 4-6 sentence plain-language read via
    ``app/generate_seafloor_report.py`` (``hf-inference`` +
    ``Qwen2.5-7B-Instruct``). Yields (explanation_md, telemetry) tuples.
    The LLM narrates the provided stats only — it never invents numbers.
    """
    logs: list[str] = []

    def emit(explanation_md):
        return (explanation_md, _telemetry(logs))

    if not selected_break:
        logs.append("⚠️ No break selected — pick one first.")
        yield emit("_No explanation yet — pick a break first._")
        return
    lat, lng = get_coords(selected_break)
    if lat is None or lng is None:
        logs.append(f"⚠️ No coordinates for {selected_break.get('name', '?')}.")
        yield emit("_No explanation yet — break has no coordinates._")
        return
    try:
        radius = max(0.3, min(5.0, float(radius_km or 1.2)))
    except (TypeError, ValueError):
        radius = 1.2
    try:
        from legacy.app import seafloor as mod

        name = selected_break.get("name", "?")
        logs.append(
            f"🔧 [tool: get_seafloor] break='{name}' radius={radius:.1f}km "
            "(cached GEBCO grid → analyze_grid)."
        )
        progress(0.2, desc="Reading cached seafloor…")
        yield emit("_Reading cached seafloor…_")
        res = mod.get_seafloor(lat, lng, radius_km=radius)
        stats, analysis_md = res["stats"], res["analysis"]

        from legacy.app import generate_seafloor_report as rep

        logs.append(
            f"🧠 [tool: generate_seafloor_explanation_stream] InferenceClient "
            f"provider='{rep.PROVIDER}' model='{rep.MODEL_ID}' "
            f"(stream=True, temp={rep.TEMPERATURE}, max_tokens={rep.MAX_TOKENS})…"
        )
        progress(0.4, desc="Explaining seafloor…")
        shown = ""
        for text in rep.generate_seafloor_explanation_stream(
            break_=selected_break, stats=stats, analysis=analysis_md
        ):
            if text.strip() and text != shown:
                shown = text
                yield emit(shown)
        if not shown.strip():
            raise ValueError("Empty stream from seafloor explainer.")
        logs.append(f"✅ Done → {len(shown)} chars.")
        progress(1.0, desc="Done")
        yield emit(shown)
    except Exception as e:  # noqa: BLE001 — LLM failure keeps deterministic charts
        logs.append(f"❌ Explanation failed: {e}")
        logs.append("💡 Check HF_TOKEN is set and hf-inference serves the model.")
        logs.append("ℹ️ Deterministic stats above still apply.")
        yield emit("_Explanation failed — deterministic stats above still apply._")
