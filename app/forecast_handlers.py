"""Swell-check handlers: deterministic forecast charts + AI report."""

from __future__ import annotations

import time

import gradio as gr
from plotly import graph_objects as go

from app.config import _NO_REPORT_MD
from app.custom_break import _telemetry

def _empty_forecast_fig() -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text="No forecast data", showarrow=False, font={"size": 16})
    return fig


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

        from app import surf_forecast as mod
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
        from app import generate_surf_report as rep
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
