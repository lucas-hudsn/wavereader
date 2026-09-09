"""Browse-tab state: selection, filtering, map refresh, mode-toggle sync."""

from __future__ import annotations

import gradio as gr
import pandas as pd

from app.break_details import _CAM_EMPTY_MD, _cam_entry, _cam_markdown, break_to_table
from app.breaks_data import ALL_REGIONS, DF, REGIONS_BY_STATE, filter_breaks
from app.config import AGENT_INTRO, ALL, BROWSE_INTRO, SKILL_ORDER, _NO_BREAK_HEADER
from app.maps import build_map_with_custom

def on_mode_change(agentic: bool):
    """Toggle between browse UI and the agent-only interface (slide switch)."""
    is_agent = bool(agentic)
    return (
        gr.update(visible=not is_agent),
        gr.update(visible=is_agent),
        AGENT_INTRO if is_agent else BROWSE_INTRO,
    )


def go_to_forecast():
    """Leave agentic mode and jump the browse tabs to the forecast page."""
    return (
        gr.Tabs(selected="forecast"),
        gr.update(value=False),
        gr.update(visible=True),
        gr.update(visible=False),
        BROWSE_INTRO,
    )


def _records(df: pd.DataFrame) -> list[dict]:
    return df.to_dict(orient="records")


def _effective_names(base_records: list[dict], custom: dict | None) -> list[str]:
    names = [r.get("name", "?") for r in base_records]
    if custom and custom.get("name"):
        names = [*names, f"{custom['name']} ⭐ (your break)"]
    return names


def _break_list_label(names: list[str]) -> str:
    """Break-checklist label with the live spot count folded in."""
    return f"Breaks (pick one for details) — {len(names)} spot(s)"


def _resolve_pick(break_label: str, base_records: list[dict], custom: dict | None) -> dict | None:
    """Map a Break-list label back to its record (custom break has a ⭐ suffix)."""
    if custom and break_label == f"{custom.get('name', '')} ⭐ (your break)":
        return custom
    for r in base_records:
        if r.get("name") == break_label:
            return r
    return None


def update_map(state: str, region: str, skill: str, custom: dict | None):
    """Re-filter, rebuild the map (with custom highlight), refresh break choices.

    The spot count lives in the break-checklist label (no separate count
    display) and both tab pickers (break book + swell check) get the same
    choices so users can iterate forecasts without switching tabs.
    """
    df = filter_breaks(DF, state, region, skill)
    records = _records(df)
    unfiltered = all(v in (None, ALL) for v in (state, region, skill))
    fig = build_map_with_custom(records, custom, default_view=unfiltered)
    names = _effective_names(records, custom)
    label = _break_list_label(names)
    picker_update = gr.update(choices=names, value=None, label=label)
    return (
        fig,
        picker_update,
        picker_update,
        records,
        pd.DataFrame(columns=["Field", "Value"]),
        _CAM_EMPTY_MD,
    )


def update_region_choices(state: str):
    regions = REGIONS_BY_STATE.get(state, ALL_REGIONS) if state != ALL else ALL_REGIONS
    return gr.update(choices=[ALL, *regions], value=ALL)


def update_custom_regions(state: str):
    regions = REGIONS_BY_STATE.get(state, ALL_REGIONS)
    return gr.update(choices=[*regions], value=None)


def sync_custom_from_filters(state: str, region: str):
    """Push the main map State/Region filters into the generation form.

    A specific filter value overwrites the custom form so the wave-data
    generation function (``generate_surf_break``) runs in the same filtered
    context as the map; ``ALL`` leaves that field untouched (``gr.skip``).
    """
    if state and state != ALL:
        regions = REGIONS_BY_STATE.get(state, ALL_REGIONS)
        state_update = gr.update(value=state)
    else:
        regions = ALL_REGIONS
        state_update = gr.skip()
    if region and region != ALL:
        choices = [*regions] if region in regions else [*regions, region]
        region_update = gr.update(choices=choices, value=region)
    else:
        region_update = gr.update(choices=[*regions])
    return state_update, region_update


def _regions_for(state: str | None) -> list[str]:
    """Region choices valid for a state filter (ALL state → every region)."""
    return REGIONS_BY_STATE.get(state, ALL_REGIONS) if state != ALL else ALL_REGIONS


def mirror_browse_to_prefs(state: str, region: str):
    """Copy the browse State/Region filters into the agent preferences.

    Live one-way leg of the browse↔agent selection sync (safe: dropdown
    values + context chip only, never touches the map or picks).
    """
    regions = _regions_for(state)
    region_val = region if region in [ALL, *regions] else ALL
    return (
        gr.update(value=state),
        gr.update(choices=[ALL, *regions], value=region_val),
    )


def mirror_prefs_to_browse(pref_state: str, pref_region: str):
    """Copy the agent State/Region prefs into the browse filter values.

    Value-only on purpose: the map + pickers rebuild lazily in
    ``resync_on_mode_toggle`` when returning to browse mode, so tweaking
    prefs mid-chat never clobbers the break pick or details panel.
    """
    regions = _regions_for(pref_state)
    region_val = pref_region if pref_region in [ALL, *regions] else ALL
    return (
        gr.update(value=pref_state),
        gr.update(choices=[ALL, *regions], value=region_val),
    )


def mirror_filter_skill_to_scoring(filter_skill: str):
    """Push a concrete map-filter skill into both scoring skills.

    ``ALL`` (no filter) leaves the scoring skills untouched — filtering and
    scoring are different concepts, only a concrete level carries over.
    """
    if filter_skill and filter_skill != ALL and filter_skill in SKILL_ORDER:
        return gr.update(value=filter_skill), gr.update(value=filter_skill)
    return gr.skip(), gr.skip()


def mirror_scoring_skill(skill: str):
    """Mirror one scoring skill dropdown onto the other (they share choices)."""
    if skill and skill in SKILL_ORDER:
        return gr.update(value=skill)
    return gr.skip()


def resync_on_mode_toggle(
    agentic: bool,
    state: str,
    region: str,
    filter_skill: str,
    fc_skill: str,
    pref_state: str,
    pref_region: str,
    agent_skill: str,
    stance: str,
    selected: dict | None,
    custom: dict | None,
):
    """Reconcile browse filters ↔ agent prefs on the agentic-mode toggle.

    Live mirrors keep dropdown *values* in sync while interacting, but the
    map rebuild is deferred here so agent-side tweaks never wipe the break
    pick mid-chat. Entering agent mode copies browse filters → prefs;
    entering browse mode copies prefs → filters and rebuilds the map while
    preserving the selected break's highlight/details when it still matches.
    Outputs: [state_dd, region_dd, map, break_dd, fc_break_dd, records,
    details, cam, custom_state, custom_region, pref_state, pref_region,
    agent_skill, fc_skill, pref_chip] (untouched direction gets gr.skip()).
    """
    empty_details = pd.DataFrame(columns=["Field", "Value"])
    if bool(agentic):
        regions = _regions_for(state)
        region_val = region if region in [ALL, *regions] else ALL
        skill_val = fc_skill if fc_skill in SKILL_ORDER else agent_skill
        chip = _format_pref_chip(state, region_val, skill_val, stance, selected)
        return (
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.skip(),
            gr.update(value=state),
            gr.update(choices=[ALL, *regions], value=region_val),
            gr.update(value=skill_val),
            gr.skip(),
            chip,
        )
    regions = _regions_for(pref_state)
    region_val = pref_region if pref_region in [ALL, *regions] else ALL
    eff_state = pref_state if pref_state else ALL
    df = filter_breaks(DF, eff_state, region_val, filter_skill)
    records = _records(df)
    unfiltered = all(v in (None, ALL) for v in (eff_state, region_val, filter_skill))
    fig = build_map_with_custom(records, custom, default_view=unfiltered)
    names = _effective_names(records, custom)
    keep = None
    details = empty_details
    cam = _CAM_EMPTY_MD
    if selected and selected.get("name"):
        if str(selected.get("id", "")).startswith("session-only"):
            cand = f"{selected.get('name', '')} ⭐ (your break)"
        else:
            cand = selected.get("name")
        if cand in names:
            keep = cand
            details = break_to_table(selected)
            cam = _cam_markdown(selected)
    picker = gr.update(choices=names, value=keep, label=_break_list_label(names))
    custom_state_update, custom_region_update = sync_custom_from_filters(
        eff_state, region_val
    )
    return (
        gr.update(value=eff_state),
        gr.update(choices=[ALL, *regions], value=region_val),
        fig,
        picker,
        picker,
        records,
        details,
        cam,
        custom_state_update,
        custom_region_update,
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
        gr.skip(),
    )


def on_break_pick(break_label: str, records: list[dict], custom: dict | None):
    """Update details + shared forecast state when either break list changes.

    Also refreshes the forecast-tab header and both skill defaults (the
    forecast dropdown and the agent-tab skill), and mirrors the pick into
    the other tab's checklist so both pages stay consistent. Works for
    base records and the custom ⭐ break via ``_resolve_pick``.
    """
    empty_details = pd.DataFrame(columns=["Field", "Value"])
    if not break_label:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip(), gr.skip(), gr.skip(), gr.skip(), _CAM_EMPTY_MD
    record = _resolve_pick(break_label, records or [], custom)
    if record is None:
        return empty_details, None, _NO_BREAK_HEADER, gr.skip(), gr.skip(), gr.skip(), gr.skip(), _CAM_EMPTY_MD
    raw_skill = str(record.get("skillLevel") or "intermediate").strip().lower()
    skill_value = raw_skill if raw_skill in SKILL_ORDER else "intermediate"
    # Browse forecast skill + agent skill share SKILL_ORDER choices, so one
    # value keeps both scoring paths consistent.
    agent_skill_value = skill_value
    header = (
        f"### {record.get('name', '?')} — "
        f"{record.get('region', '?')}, {record.get('state', '?')}"
    )
    entry = _cam_entry(record)
    if entry and entry.get("url"):
        header += f"\n🎥 Live cam: [{entry.get('label', 'Live cam')}]({entry['url']})"
    cam_md = _cam_markdown(record)
    pick_update = gr.update(value=break_label)
    return (
        break_to_table(record),
        record,
        header,
        gr.update(value=skill_value),
        gr.update(value=agent_skill_value),
        pick_update,
        pick_update,
        cam_md,
    )


def _format_pref_chip(
    pref_state: str | None,
    pref_region: str | None,
    skill: str | None,
    stance: str | None,
    selected_break: dict | None,
) -> str:
    """Render the surf-agent context chip (active prefs + encyclopedia pick)."""
    state = pref_state if pref_state and pref_state != ALL else "All"
    region = pref_region if pref_region and pref_region != ALL else "All"
    skill_txt = (skill or "intermediate").strip().lower()
    stance_txt = (stance or "no preference").strip().lower()
    if selected_break and selected_break.get("name"):
        ctx = ", ".join(
            p
            for p in (
                selected_break.get("name"),
                selected_break.get("region"),
                selected_break.get("state"),
            )
            if p
        )
        viewing = ctx or selected_break.get("name")
    else:
        viewing = "none"
    return (
        f"_Prefs: state={state} · region={region} · skill={skill_txt} · "
        f"stance={stance_txt} · viewing={viewing}_"
    )
