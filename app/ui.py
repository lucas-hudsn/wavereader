"""Gradio layout + event wiring (build_demo)."""

from __future__ import annotations

import gradio as gr

from app.agent_chat import (
    chat_fn,
    clear_agent_chat,
    on_agent_spot_change,
    on_rank_select,
)
from app.break_details import _CAM_EMPTY_MD
from app.breaks_data import ALL_REGIONS, DF, SKILLS, STATES
from app.browse_sync import (
    _format_pref_chip,
    _records,
    go_to_forecast,
    mirror_browse_to_prefs,
    mirror_filter_skill_to_scoring,
    mirror_prefs_to_browse,
    mirror_scoring_skill,
    on_break_pick,
    on_mode_change,
    resync_on_mode_toggle,
    sync_custom_from_filters,
    update_custom_regions,
    update_map,
    update_region_choices,
)
from app.config import (
    AGENT_MODE_LABEL,
    ALL,
    BROWSE_INTRO,
    SCORE_EXPLAINER_MD,
    SKILL_ORDER,
    _NO_BREAK_HEADER,
    _NO_REPORT_MD,
)
from app.custom_break import clear_custom_break, generate_custom_break
from app.forecast_handlers import fetch_forecast, generate_reports
from app.maps import build_map
from app.seafloor_handlers import fetch_seafloor, generate_seafloor_explanation


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="wave~reader — break book + swell check") as demo:
        with gr.Row(elem_classes=["header-row"]):
            with gr.Column(scale=9):
                gr.Markdown("# wave~reader", elem_classes=["hero-title"])
                gr.Markdown(
                    "powered by [Hugging Face Inference Providers](https://huggingface.co/inference/models) "
                    "· [NVIDIA Nemotron 3](https://huggingface.co/collections/nvidia/nvidia-nemotron-v3)",
                    elem_classes=["hero-sub"],
                )
                intro_md = gr.Markdown(BROWSE_INTRO)
            with gr.Column(scale=1, min_width=240, elem_classes=["mode-switch-wrap"]):
                mode_toggle = gr.Checkbox(
                    value=False,
                    label=AGENT_MODE_LABEL,
                    elem_classes=["mode-switch"],
                    container=True,
                )
        records_state = gr.State(_records(DF))
        custom_state = gr.State(None)  # one session-only break; never persisted
        selected_break = gr.State(None)  # shared pick for the forecast tab
        scored_state = gr.State(None)  # stage-1 scored payload feeding stage-2 report
        agent_session = gr.State(None)  # session-persistent SurfAgent instance
        agent_token_used = gr.State("")  # hf_token key the session agent was built with
        agent_conv = gr.State([])  # explicit conversation history for fresh agents
        agent_charts = gr.State(None)  # all score_week payloads + rank payload
        with gr.Group(visible=True) as browse_group:
            with gr.Tabs() as tabs:
                with gr.Tab("break book", id="encyclopedia"):
                    gr.Markdown("### break book")
                    gr.Markdown("filter spots, hover a dot for its name, then pick a break for details.")
                    with gr.Row():
                        state_dd = gr.Dropdown([ALL, *STATES], value=ALL, label="State")
                        region_dd = gr.Dropdown([ALL, *ALL_REGIONS], value=ALL, label="Region")
                        skill_dd = gr.Dropdown([ALL, *SKILLS], value=ALL, label="Skill level")
                    with gr.Row():
                        with gr.Column(scale=3):
                            map_plot = gr.Plot(build_map(_records(DF), default_view=True), label="Spots")
                            cant_find_btn = gr.Button(
                                "Can't find your local break?", variant="primary"
                            )
                            with gr.Group(visible=False) as custom_box:
                                gr.Markdown(
                                    "### Generate your local break\n"
                                    "One break per session, generated live via "
                                    "`app/generate_surf_break.py`. Session-only — "
                                    "never saved, deleted when your session ends."
                                )
                                with gr.Row():
                                    custom_state_dd = gr.Dropdown(
                                        STATES, value=None, label="State"
                                    )
                                    custom_region_dd = gr.Dropdown(
                                        ALL_REGIONS,
                                        value=None,
                                        label="Region (or type a new one)",
                                        allow_custom_value=True,
                                    )
                                custom_name_txt = gr.Textbox(
                                    label="Break name", placeholder="e.g. Kilcunda"
                                )
                                with gr.Row():
                                    generate_btn = gr.Button("Generate my break", variant="primary")
                                    clear_btn = gr.Button("Delete my break", variant="stop")
                                telemetry_box = gr.Textbox(
                                    label="Generation telemetry (tool calls)",
                                    lines=8,
                                    max_lines=14,
                                    interactive=False,
                                    placeholder="Press “Generate my break” to see the tool-call trace…",
                                )
                        with gr.Column(scale=2):
                            break_dd = gr.Radio(
                                choices=[r.get("name", "?") for r in _records(DF)],
                                value=None,
                                label=f"Breaks (pick one for details) — {len(DF)} spot(s)",
                                elem_classes=["break-list"],
                            )
                            details_df = gr.Dataframe(
                                headers=["Field", "Value"],
                                row_count=(17, "fixed"),
                                column_count=(2, "fixed"),
                                label="Break details",
                                wrap=True,
                            )
                            cam_md = gr.Markdown(_CAM_EMPTY_MD)
                            go_forecast_btn = gr.Button(
                                "Check swell →", variant="primary"
                            )
                with gr.Tab("swell check", id="forecast"):
                    gr.Markdown("### swell check")
                    gr.Markdown(
                        "pick a break below — charts load automatically "
                        "+ an optional ai report."
                    )
                    fc_break_dd = gr.Radio(
                        choices=[r.get("name", "?") for r in _records(DF)],
                        value=None,
                        label=f"Breaks (pick one for details) — {len(DF)} spot(s)",
                        elem_classes=["break-list"],
                    )
                    fc_header = gr.Markdown(_NO_BREAK_HEADER)
                    fc_skill = gr.Dropdown(
                        SKILL_ORDER, value="intermediate", label="Skill level"
                    )
                    status_box = gr.Textbox(
                        label="Status",
                        interactive=False,
                        placeholder="Pick a break — forecast loads automatically…",
                    )
                    with gr.Tabs():
                        with gr.Tab("Score"):
                            score_plot = gr.Plot(label="Score (0-10)")
                            with gr.Accordion("how the score is calculated", open=False):
                                gr.Markdown(SCORE_EXPLAINER_MD)
                        with gr.Tab("Swell"):
                            waves_plot = gr.Plot(label="Swell")
                        with gr.Tab("Wind"):
                            wind_plot = gr.Plot(label="Wind (kt)")
                        with gr.Tab("Seafloor"):
                            gr.Markdown(
                                "world model — GEBCO bathymetry around the takeoff zone "
                                "(blue = deep, green = land, ★ = break). auto-loads "
                                "with the forecast above."
                            )
                            with gr.Row():
                                seafloor_radius = gr.Slider(
                                    0.5, 3.0, value=1.2, step=0.1,
                                    label="Box half-width (km)",
                                )
                                seafloor_refresh = gr.Button(
                                    "Refresh seafloor 🌊", variant="secondary"
                                )
                            seafloor_status = gr.Textbox(
                                label="Seafloor status",
                                interactive=False,
                                placeholder="Pick a break — seafloor loads automatically…",
                            )
                            seafloor_depth_plot = gr.Plot(label="Depth map")
                            seafloor_surface_plot = gr.Plot(label="3D seafloor")
                            seafloor_transect_plot = gr.Plot(label="Transects")
                            seafloor_md = gr.Markdown(
                                "_Pick a break — its seafloor model loads automatically._"
                            )
                            explain_seafloor_btn = gr.Button(
                                "Explain seafloor ✨", variant="secondary"
                            )
                            seafloor_explain_md = gr.Markdown(
                                "_Press “Explain seafloor ✨” for a plain-language read (free-tier model)._"
                            )
                            seafloor_telemetry_box = gr.Textbox(
                                label="Seafloor telemetry (tool calls)",
                                lines=6,
                                max_lines=12,
                                interactive=False,
                                placeholder="Pick a break for the GEBCO trace…",
                            )
                    report_btn = gr.Button("Generate surf report ✨", variant="secondary")
                    report_md = gr.Markdown(_NO_REPORT_MD)
                    report_telemetry_box = gr.Textbox(
                        label="Report telemetry (tool calls)",
                        lines=8,
                        max_lines=14,
                        interactive=False,
                        placeholder="Pick a break for auto scoring trace, then “Generate surf report”…",
                    )
        with gr.Group(visible=False) as agent_group:
            gr.Markdown("### Agentic mode")
            gr.Markdown(
                "chat with the smolagents surf agent (`app/agent.py`) — it calls "
                "forecast/scoring tools and explains in the chat. "
                "charts + leaderboard appear below only when the agent "
                "actually scores a spot. pick a break in browse mode for "
                "context, or just name one in your question."
            )
            with gr.Row():
                pref_state = gr.Dropdown(
                    [ALL, *STATES], value=ALL, label="State preference"
                )
                pref_region = gr.Dropdown(
                    [ALL, *ALL_REGIONS], value=ALL, label="Region preference"
                )
                agent_skill = gr.Dropdown(
                    SKILL_ORDER,
                    value="intermediate",
                    label="Skill level",
                )
                stance_dd = gr.Dropdown(
                    ["natural", "goofy", "no preference"],
                    value="no preference",
                    label="Stance",
                )
                daypart_dd = gr.Dropdown(
                    ["all day", "mornings", "weekend"],
                    value="all day",
                    label="When",
                )
            pref_chip = gr.Markdown(
                "_Prefs: state=All · region=All · skill=intermediate · "
                "stance=no preference · viewing=none_"
            )
            with gr.Row():
                agent_token = gr.Textbox(
                    label="HF token (optional)",
                    type="password",
                    placeholder="Defaults to HF_TOKEN env — per-session override, never logged.",
                )
            with gr.Row():
                chip1 = gr.Button("Best in NSW this weekend (beginner)", variant="secondary")
                chip2 = gr.Button("Bells Beach mornings?", variant="secondary")
                chip3 = gr.Button("Quieter like Snapper?", variant="secondary")
                chip4 = gr.Button("Wetsuit + sunrise at Noosa?", variant="secondary")
            with gr.Group(elem_classes=["chat-panel"]):
                agent_chat = gr.Chatbot(label="Surf agent", height=420)
                with gr.Row(elem_classes=["chat-input-row"]):
                    agent_msg = gr.Textbox(
                        show_label=False,
                        value="What does the surf look like this morning?",
                        placeholder="e.g. When should I surf Bells Beach this week? (Enter to send)",
                        container=False,
                        scale=8,
                    )
                    agent_send = gr.Button("Send", variant="primary", scale=1)
                    agent_clear = gr.Button("Clear", variant="stop", scale=1)
            agent_telemetry_box = gr.Textbox(
                label="Agent activity (live tool calls)",
                lines=8,
                max_lines=14,
                interactive=False,
                placeholder="Send a question — tools start/finish here live, e.g. scoring Bells Beach…",
            )
            agent_status_box = gr.Textbox(
                label="Status",
                interactive=False,
                placeholder="Ask about a break — charts appear as each spot is scored…",
            )
            with gr.Group(visible=False) as agent_charts_group:
                agent_best_md = gr.Markdown("_No agent answer yet._")
                agent_spot_dd = gr.Dropdown(
                    choices=[],
                    value=None,
                    visible=False,
                    label="Chart spot (multiple scored)",
                )
                with gr.Tabs():
                    with gr.Tab("Score"):
                        agent_score_plot = gr.Plot(label="Score (0-10)")
                        with gr.Accordion("how the score is calculated", open=False):
                            gr.Markdown(SCORE_EXPLAINER_MD)
                    with gr.Tab("Swell"):
                        agent_waves_plot = gr.Plot(label="Swell")
                    with gr.Tab("Wind"):
                        agent_wind_plot = gr.Plot(label="Wind (kt)")
            with gr.Group(visible=False) as agent_rank_group:
                agent_rank_df = gr.Dataframe(
                    headers=["Rank", "Spot", "Region", "Best score", "Best time"],
                    label="Leaderboard (rank / region sweep — click a row to ask about it)",
                    wrap=True,
                )

        def _toggle_custom_box(visible: bool):
            return gr.update(visible=not visible), not visible

        box_visible = gr.State(False)
        cant_find_btn.click(
            _toggle_custom_box,
            inputs=box_visible,
            outputs=[custom_box, box_visible],
        )
        custom_state_dd.change(
            update_custom_regions,
            inputs=custom_state_dd,
            outputs=custom_region_dd,
        )

        state_dd.change(
            update_region_choices, inputs=state_dd, outputs=region_dd
        ).then(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df, cam_md],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        ).then(
            mirror_browse_to_prefs,
            inputs=[state_dd, region_dd],
            outputs=[pref_state, pref_region],
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        region_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df, cam_md],
        ).then(
            sync_custom_from_filters,
            inputs=[state_dd, region_dd],
            outputs=[custom_state_dd, custom_region_dd],
        ).then(
            mirror_browse_to_prefs,
            inputs=[state_dd, region_dd],
            outputs=[pref_state, pref_region],
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        skill_dd.change(
            update_map,
            inputs=[state_dd, region_dd, skill_dd, custom_state],
            outputs=[map_plot, break_dd, fc_break_dd, records_state, details_df, cam_md],
        ).then(
            mirror_filter_skill_to_scoring,
            inputs=skill_dd,
            outputs=[fc_skill, agent_skill],
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        break_dd.change(
            on_break_pick,
            inputs=[break_dd, records_state, custom_state],
            outputs=[details_df, selected_break, fc_header, fc_skill, agent_skill, break_dd, fc_break_dd, cam_md],
        ).then(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        ).then(
            fetch_seafloor,
            inputs=[selected_break, seafloor_radius],
            outputs=[
                seafloor_status,
                seafloor_depth_plot,
                seafloor_surface_plot,
                seafloor_transect_plot,
                seafloor_md,
                seafloor_telemetry_box,
                seafloor_explain_md,
            ],
        )
        fc_break_dd.change(
            on_break_pick,
            inputs=[fc_break_dd, records_state, custom_state],
            outputs=[details_df, selected_break, fc_header, fc_skill, agent_skill, break_dd, fc_break_dd, cam_md],
        ).then(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        ).then(
            fetch_seafloor,
            inputs=[selected_break, seafloor_radius],
            outputs=[
                seafloor_status,
                seafloor_depth_plot,
                seafloor_surface_plot,
                seafloor_transect_plot,
                seafloor_md,
                seafloor_telemetry_box,
                seafloor_explain_md,
            ],
        )
        seafloor_radius.change(
            fetch_seafloor,
            inputs=[selected_break, seafloor_radius],
            outputs=[
                seafloor_status,
                seafloor_depth_plot,
                seafloor_surface_plot,
                seafloor_transect_plot,
                seafloor_md,
                seafloor_telemetry_box,
                seafloor_explain_md,
            ],
        )
        seafloor_refresh.click(
            fetch_seafloor,
            inputs=[selected_break, seafloor_radius],
            outputs=[
                seafloor_status,
                seafloor_depth_plot,
                seafloor_surface_plot,
                seafloor_transect_plot,
                seafloor_md,
                seafloor_telemetry_box,
                seafloor_explain_md,
            ],
        )
        explain_seafloor_btn.click(
            generate_seafloor_explanation,
            inputs=[selected_break, seafloor_radius],
            outputs=[
                seafloor_explain_md,
                seafloor_telemetry_box,
            ],
        )
        fc_skill.change(
            fetch_forecast,
            inputs=[selected_break, fc_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        ).then(
            mirror_scoring_skill,
            inputs=fc_skill,
            outputs=agent_skill,
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        mode_toggle.change(
            on_mode_change,
            inputs=mode_toggle,
            outputs=[browse_group, agent_group, intro_md],
        ).then(
            resync_on_mode_toggle,
            inputs=[
                mode_toggle,
                state_dd,
                region_dd,
                skill_dd,
                fc_skill,
                pref_state,
                pref_region,
                agent_skill,
                stance_dd,
                selected_break,
                custom_state,
            ],
            outputs=[
                state_dd,
                region_dd,
                map_plot,
                break_dd,
                fc_break_dd,
                records_state,
                details_df,
                cam_md,
                custom_state_dd,
                custom_region_dd,
                pref_state,
                pref_region,
                agent_skill,
                fc_skill,
                pref_chip,
            ],
        )
        go_forecast_btn.click(
            go_to_forecast,
            inputs=None,
            outputs=[tabs, mode_toggle, browse_group, agent_group, intro_md],
        )
        generate_btn.click(
            generate_custom_break,
            inputs=[
                custom_name_txt,
                custom_state_dd,
                custom_region_dd,
                records_state,
                custom_state,
                state_dd,
                region_dd,
            ],
            outputs=[telemetry_box, details_df, map_plot, break_dd, fc_break_dd, custom_state, cam_md],
        )
        clear_btn.click(
            clear_custom_break,
            inputs=[records_state, selected_break],
            outputs=[
                custom_state,
                telemetry_box,
                details_df,
                map_plot,
                break_dd,
                fc_break_dd,
                selected_break,
                fc_header,
                fc_skill,
                cam_md,
            ],
        )
        report_btn.click(
            generate_reports,
            inputs=[scored_state],
            outputs=[
                report_md,
                report_telemetry_box,
            ],
        )
        pref_state.change(
            update_region_choices, inputs=pref_state, outputs=pref_region
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        ).then(
            mirror_prefs_to_browse,
            inputs=[pref_state, pref_region],
            outputs=[state_dd, region_dd],
        )
        pref_region.change(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        ).then(
            mirror_prefs_to_browse,
            inputs=[pref_state, pref_region],
            outputs=[state_dd, region_dd],
        )
        agent_skill.change(
            fetch_forecast,
            inputs=[selected_break, agent_skill],
            outputs=[
                status_box,
                score_plot,
                waves_plot,
                wind_plot,
                scored_state,
                report_telemetry_box,
                report_md,
            ],
        ).then(
            mirror_scoring_skill,
            inputs=agent_skill,
            outputs=fc_skill,
        ).then(
            _format_pref_chip,
            inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
            outputs=pref_chip,
        )
        for _comp in (stance_dd, daypart_dd):
            _comp.change(
                _format_pref_chip,
                inputs=[pref_state, pref_region, agent_skill, stance_dd, selected_break],
                outputs=pref_chip,
            )
        agent_send.click(
            chat_fn,
            inputs=[agent_msg, agent_chat, agent_skill, agent_token, selected_break, pref_state, pref_region, stance_dd, agent_skill, agent_session, agent_token_used, agent_conv, agent_charts, daypart_dd],
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        agent_msg.submit(
            chat_fn,
            inputs=[agent_msg, agent_chat, agent_skill, agent_token, selected_break, pref_state, pref_region, stance_dd, agent_skill, agent_session, agent_token_used, agent_conv, agent_charts, daypart_dd],
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        agent_spot_dd.change(
            on_agent_spot_change,
            inputs=[agent_spot_dd, agent_charts, selected_break],
            outputs=[
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
            ],
        )
        agent_clear.click(
            clear_agent_chat,
            inputs=None,
            outputs=[
                agent_chat,
                agent_msg,
                agent_telemetry_box,
                agent_status_box,
                agent_score_plot,
                agent_waves_plot,
                agent_wind_plot,
                agent_best_md,
                agent_spot_dd,
                agent_rank_df,
                agent_charts,
                agent_session,
                agent_token_used,
                agent_conv,
                agent_charts_group,
                agent_rank_group,
            ],
        )
        chip1.click(
            lambda: gr.update(value="Where should I surf in New South Wales this weekend as a beginner?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip2.click(
            lambda: gr.update(value="When are the best morning windows at Bells Beach this week?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip3.click(
            lambda: gr.update(value="What breaks are like Snapper Rocks but quieter?"),
            inputs=None,
            outputs=agent_msg,
        )
        chip4.click(
            lambda: gr.update(value="What is the water temp + sunrise/sunset for Noosa Heads this week, and what wetsuit?"),
            inputs=None,
            outputs=agent_msg,
        )
        agent_rank_df.select(
            on_rank_select,
            inputs=agent_rank_df,
            outputs=agent_msg,
        )
    return demo
