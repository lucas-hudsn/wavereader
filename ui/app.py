"""v2 Gradio 6 app: three tabs (break book / swell check / surf agent).

Exactly three session states: the shared break pick, the scored forecast
payload, and the agent chart/usage store. Filters are one-way only.
"""

from __future__ import annotations

import gradio as gr

from ui import _compat as C
from ui.panels import agent as agent_panel
from ui.panels import book as book_panel
from ui.panels import swell as swell_panel


def build() -> gr.Blocks:
    """Assemble the demo (no launch — the Space entrypoint launches)."""
    records = C.list_breaks()
    vocab = C.index_breaks(records)

    with gr.Blocks(title="wave~reader — break book + swell check") as demo:
        gr.Markdown("# wave~reader", elem_classes=["hero-title"])
        gr.Markdown("a guide to australian surf breaks — browse, score the week, or ask the agent.",
                    elem_classes=["hero-sub"])

        selected = gr.State(None)
        scored = gr.State(None)
        agent_store = gr.State(agent_panel.fresh_store())

        with gr.Tabs():
            b = book_panel.build_book(records, vocab, selected)
            s = swell_panel.build_swell(selected, scored)
            a = agent_panel.build_agent(selected, agent_store, records)

        swell_outputs = [s["header_md"], s["status_box"], s["hero_md"],
                         s["score_plot"], s["swell_plot"], s["wind_plot"],
                         s["depth_plot"], s["surface_plot"], s["transect_plot"],
                         s["seafloor_md"], scored]
        agent_outputs = [a["chatbot"], a["msg"], a["telemetry_md"], a["token_md"],
                         a["status_box"], a["agent_score"], a["agent_swell"],
                         a["agent_wind"], a["spot_dd"], a["rank_df"], agent_store]

        # -- book: one-way filters --
        b["state_dd"].change(
            b["state_regions"], inputs=b["state_dd"], outputs=b["region_dd"],
        ).then(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["break_radio"]],
        )
        b["region_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["break_radio"]],
        )
        b["skill_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["break_radio"]],
        )
        # -- book pick → details + climate + shared pick → swell fetch --
        b["break_radio"].change(
            b["pick_changed"], inputs=b["break_radio"],
            outputs=[b["details_df"], b["rose_plot"], b["audit_md"],
                     b["pick_header"], selected],
        ).then(
            s["fetch_forecast"], inputs=[selected, s["skill_dd"]], outputs=swell_outputs,
        )
        # -- swell: skill change refetches; narrate streams markdown --
        s["skill_dd"].change(
            s["fetch_forecast"], inputs=[selected, s["skill_dd"]], outputs=swell_outputs,
        )
        s["narrate_btn"].click(s["narrate"], inputs=scored, outputs=s["report_md"])
        # -- agent: chat streams tool cards + meter + charts --
        a["send_btn"].click(
            a["chat"], inputs=[a["msg"], a["chatbot"], a["skill_dd"], a["token_box"],
                               selected, agent_store], outputs=agent_outputs,
        )
        a["msg"].submit(
            a["chat"], inputs=[a["msg"], a["chatbot"], a["skill_dd"], a["token_box"],
                               selected, agent_store], outputs=agent_outputs,
        )
        a["spot_dd"].change(
            a["show_spot"], inputs=[a["spot_dd"], agent_store],
            outputs=[a["agent_score"], a["agent_swell"], a["agent_wind"]],
        )
        a["clear_btn"].click(a["clear"], inputs=None, outputs=agent_outputs)
        prompts = ["Where should I surf in New South Wales this weekend as a beginner?",
                   "When are the best morning windows at Bells Beach this week?",
                   "What breaks are like Snapper Rocks but quieter?"]
        for chip, prompt in zip(a["chips"], prompts):
            chip.click(a["chip_text"](prompt), inputs=None, outputs=a["msg"])

    return demo
