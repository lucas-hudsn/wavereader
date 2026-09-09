"""Session-only custom break generation (never written to disk)."""

from __future__ import annotations

import time

import gradio as gr
import pandas as pd

from legacy.app.break_details import _CAM_EMPTY_MD, _cam_markdown, break_to_table
from legacy.app.browse_sync import _break_list_label, _effective_names
from legacy.app.config import ALL, _NO_BREAK_HEADER
from legacy.app.maps import _lat, _lng, build_map, build_map_with_custom
from legacy.app.prompt_guard import (
    MAX_BREAK_NAME_LEN,
    MAX_STATE_REGION_LEN,
    sanitize_break_field,
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

    def emit(fig=None, details=None, choices=None, cam=_CAM_EMPTY_MD):
        return (
            _telemetry(logs),
            details if details is not None else empty_details,
            fig if fig is not None else gr.skip(),
            choices if choices is not None else gr.skip(),
            choices if choices is not None else gr.skip(),
            gr.skip(),
            cam,
        )

    # Prompt-injection guard (sanitize-and-continue): structured slots are
    # untrusted data — strip markers/controls, cap length, keep generating.
    break_name, name_changed = sanitize_break_field(break_name, MAX_BREAK_NAME_LEN)
    raw_state, state_changed = sanitize_break_field(custom_state, MAX_STATE_REGION_LEN)
    raw_region, region_changed = sanitize_break_field(custom_region, MAX_STATE_REGION_LEN)
    if name_changed or state_changed or region_changed:
        logs.append("🧹 Cleaned break inputs (trimmed markers/length) — continuing.")
    # Fall back to the main map filters when the custom field is empty.
    state = raw_state
    if not state and filter_state and filter_state != ALL:
        state, _ = sanitize_break_field(filter_state, MAX_STATE_REGION_LEN)
        logs.append(f"↪ Using map filter state='{state}'.")
    region = raw_region
    if not region and filter_region and filter_region != ALL:
        region, _ = sanitize_break_field(filter_region, MAX_STATE_REGION_LEN)
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
        from legacy.app import generate_surf_break as gen
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
        # Canonical inputs win: a prompt-injected model reply can't rename
        # the break or move it to another state/region.
        custom["name"] = break_name
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
        picker_update = gr.update(
            choices=names,
            value=f"{custom.get('name', '')} ⭐ (your break)",
            label=_break_list_label(names),
        )
        yield (
            _telemetry(logs),
            details,
            fig,
            picker_update,
            picker_update,
            custom,
            _cam_markdown(custom),
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
    picker_update = gr.update(choices=names, value=None, label=_break_list_label(names))
    return (
        None,
        "🗑️ Session break deleted.",
        pd.DataFrame(columns=["Field", "Value"]),
        fig,
        picker_update,
        picker_update,
        picker_update,
        None if was_selected_custom else gr.skip(),
        _NO_BREAK_HEADER if was_selected_custom else gr.skip(),
        gr.skip(),
        _CAM_EMPTY_MD,
    )
