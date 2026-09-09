"""v2 Gradio 6 app: three tabs (break book / swell check / surf agent).

Exactly three session states: the shared break pick, the scored forecast
payload, and the agent chart/usage store. Filters are one-way only.

On load, a background thread warms forecast + seafloor caches for featured
breaks so the first click never shows a cold fetch — the engines
(world model / feeds / scorer / LLM) are named in the strip under the hero.
"""

from __future__ import annotations

import threading

import gradio as gr

from ui import _compat as C
from ui.panels import agent as agent_panel
from ui.panels import book as book_panel
from ui.panels import swell as swell_panel

_FEATURED = ["Bells Beach", "Snapper Rocks", "Bondi Beach", "Shipstern Bluff"]


def _warm_caches(records: list[dict]) -> None:
    """Pre-fetch forecast + GEBCO grids for featured breaks (daemon thread)."""

    def work():
        for name in _FEATURED:
            b = C.find_break(records, name)
            if b is None:
                continue
            try:
                C.get_scored_week(b, skill="intermediate", days=7)
            except Exception:  # noqa: BLE001 — warming must never break the UI
                pass
            try:
                C.get_seafloor(b)
            except Exception:  # noqa: BLE001
                pass

    threading.Thread(target=work, daemon=True).start()


def build() -> gr.Blocks:
    """Assemble the demo (no launch — the Space entrypoint launches)."""
    records = C.list_breaks()
    vocab = C.index_breaks(records)

    def _kick_warmup():
        _warm_caches(records)
        return None

    with gr.Blocks(title="wave~reader — break book + swell check") as demo:
        gr.Markdown("# wave~reader", elem_classes=["hero-title"])
        gr.Markdown("a guide to australian surf breaks — browse, score the week, or ask the agent.",
                    elem_classes=["hero-sub"])
        gr.Markdown(C.engine_strip(), elem_classes=["hero-sub"])
        gr.Markdown("_MCP ready — `/gradio_api/mcp/` · `score_week` / `rank_region_week` / `explain_score`_",
                    elem_classes=["hero-sub"])

        selected = gr.State(None)
        scored = gr.State(None)
        agent_store = gr.State(agent_panel.fresh_store())

        with gr.Tabs():
            b = book_panel.build_book(records, vocab, selected)
            s = swell_panel.build_swell(selected, scored)
            a = agent_panel.build_agent(selected, agent_store, records)

        # Internal listeners stay off the API/MCP surface — only the three
        # typed ``gr.api`` tools (score_week / rank_region_week /
        # explain_score) are exposed.
        demo.load(_kick_warmup, inputs=None, outputs=None, api_name=False)

        swell_outputs = [s["header_md"], s["status_box"], s["hero_md"],
                         s["score_plot"], s["swell_plot"], s["wind_plot"],
                         s["depth_plot"], s["surface_plot"], s["transect_plot"],
                         s["seafloor_md"], scored]
        agent_outputs = [a["chatbot"], a["msg"], a["telemetry_md"], a["token_md"],
                         a["status_box"], a["agent_score"], a["agent_swell"],
                         a["agent_wind"], a["spot_dd"], a["rank_df"], agent_store]

        # -- book: one-way filters (also reset details on empty result) --
        _filter_outputs = [b["map_plot"], b["break_radio"], b["details_df"],
                           b["rose_plot"], b["audit_md"], b["pick_header"]]
        b["state_dd"].change(
            b["state_regions"], inputs=b["state_dd"], outputs=b["region_dd"],
            api_name=False,
        ).then(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=_filter_outputs, api_name=False,
        )
        b["region_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=_filter_outputs, api_name=False,
        )
        b["skill_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=_filter_outputs, api_name=False,
        )
        # -- book pick → details + climate + shared pick → swell fetch --
        b["break_radio"].change(
            b["pick_changed"], inputs=b["break_radio"],
            outputs=[b["details_df"], b["rose_plot"], b["audit_md"],
                     b["pick_header"], selected],
            api_name=False,
        ).then(
            s["fetch_forecast"], inputs=[selected, s["skill_dd"]], outputs=swell_outputs,
            show_progress="minimal", api_name=False,
        )
        # -- swell: skill change refetches; narrate streams markdown --
        s["skill_dd"].change(
            s["fetch_forecast"], inputs=[selected, s["skill_dd"]], outputs=swell_outputs,
            show_progress="minimal", api_name=False,
        )
        s["narrate_btn"].click(s["narrate"], inputs=scored, outputs=s["report_md"],
                               show_progress="minimal", api_name=False)
        # -- agent: chat streams tool cards + meter + charts --
        a["send_btn"].click(
            a["chat"], inputs=[a["msg"], a["chatbot"], a["skill_dd"], a["token_box"],
                               selected, agent_store], outputs=agent_outputs,
            show_progress="minimal", api_name=False,
        )
        a["msg"].submit(
            a["chat"], inputs=[a["msg"], a["chatbot"], a["skill_dd"], a["token_box"],
                               selected, agent_store], outputs=agent_outputs,
            show_progress="minimal", api_name=False,
        )
        a["spot_dd"].change(
            a["show_spot"], inputs=[a["spot_dd"], agent_store],
            outputs=[a["agent_score"], a["agent_swell"], a["agent_wind"]],
            api_name=False,
        )
        a["clear_btn"].click(a["clear"], inputs=None, outputs=agent_outputs,
                             api_name=False)
        prompts = ["Where should I surf in New South Wales this weekend as a beginner?",
                   "When are the best morning windows at Bells Beach this week?",
                   "What breaks are like Snapper Rocks but quieter?"]
        for chip, prompt in zip(a["chips"], prompts):
            chip.click(a["chip_text"](prompt), inputs=None, outputs=a["msg"],
                       api_name=False)

    return demo
