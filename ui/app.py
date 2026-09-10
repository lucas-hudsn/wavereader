"""wave~reader v2 — ONE page: map lens → spot story → intel rail + agent.

No tabs. One shared ``selected`` spot drives everything: picking it in
the search box (or the load default) re-tells the whole page — badges,
week strip, world model, climatology — then auto-fetches
the staged forecast, and the agent reads the same context. Exactly three
session states: the shared pick, the scored payload, the agent store.
Filters are one-way only.

All component-output ordering comes from :mod:`ui.contracts` — handlers
yield via ``fill(KEYS, …)`` and the wiring assembles outputs the same
way, so panels and wiring can't drift apart. On load, a background
thread warms caches for featured breaks (the default spot fetches live).
"""

from __future__ import annotations

import threading

import gradio as gr

from ui import _compat as C
from ui.contracts import AGENT_KEYS, FETCH_KEYS, SELECT_KEYS
from ui.panels import agent as agent_panel
from ui.panels import intel as intel_panel
from ui.panels import lens as lens_panel
from ui.panels import story as story_panel

_DEFAULT_SPOT = "Bells Beach"
_FEATURED = ["Snapper Rocks", "Bondi Beach", "Shipstern Bluff", "Kirra"]
_MODE_FORECAST = "🌊 forecast"
_MODE_AGENT = "🤖 agentic mode"


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

    with gr.Blocks(title="wave~reader — one page to your next surf") as demo:
        # Hero band: title + mode toggle on one line, engine chips (with
        # the MCP note folded in) as a single compact strip underneath.
        with gr.Column(elem_classes=["hero-band"]):
            with gr.Row(elem_classes=["hero-row"]):
                with gr.Column(scale=5, min_width=220):
                    gr.Markdown("# wave~reader", elem_classes=["hero-title"])
                    gr.Markdown("smart forecasting for australia's coast — 238 breaks scored "
                                "hour by hour (0–10) from live marine data, real seafloor and "
                                "each spot's ideal conditions.", elem_classes=["hero-sub"])
                with gr.Column(scale=2, min_width=280, elem_classes=["hero-right"]):
                    mode_toggle = gr.Radio(
                        [_MODE_FORECAST, _MODE_AGENT], value=_MODE_FORECAST,
                        show_label=False, elem_classes=["mode-toggle"],
                        container=False)
            gr.Markdown(
                C.engine_strip(
                    "mcp ready — <code>/gradio_api/mcp/</code> · "
                    "<code>score_week</code> / <code>rank_region_week</code> / "
                    "<code>explain_score</code>"),
                elem_classes=["engine-md"])

        selected = gr.State(None)
        scored = gr.State(None)
        agent_store = gr.State(agent_panel.fresh_store())

        # Two full views share the page: the forecast dashboard and the
        # agent interface. The header toggle swaps them wholesale; both
        # stay wired so switching is instant (no refetch).
        with gr.Column(visible=True, elem_classes=["main-col"]) as main_col:
            with gr.Row():
                b = lens_panel.build_lens(records, vocab, selected)
                s = story_panel.build_story(selected, scored)
                with gr.Column(scale=3):
                    i = intel_panel.build_intel()

        a = agent_panel.build_agent(selected, agent_store, records, vocab, visible=False)

        # Footer: the machinery line — feed/scorer/world-model latencies —
        # lives below the fold, in both modes (outside the swapped columns).
        with gr.Column(elem_classes=["page-foot"]):
            f = story_panel.build_footer()

        def _switch_mode(mode: str):
            agentic = mode == _MODE_AGENT
            return gr.update(visible=not agentic), gr.update(visible=agentic)

        mode_toggle.change(_switch_mode, inputs=mode_toggle,
                           outputs=[main_col, a["agent_col"]], api_name=False)

        # Internal listeners stay off the API/MCP surface — only the three
        # typed ``gr.api`` tools (score_week / rank_region_week /
        # explain_score) are exposed.
        comp = {**b, **s, **i, **a, **f,
                "selected": selected, "scored": scored, "agent_store": agent_store}
        select_outputs = [comp[k] for k in SELECT_KEYS]
        fetch_outputs = [comp[k] for k in FETCH_KEYS]
        agent_outputs = [comp[k] for k in AGENT_KEYS]

        def _on_load():
            """First paint already tells a story: warm caches + default spot."""
            _warm_caches(records)
            record = C.find_break(records, _DEFAULT_SPOT)
            return b["select_spot"](record, None, fly=False)

        demo.load(_on_load, inputs=None, outputs=select_outputs, api_name=False).then(
            s["fetch_forecast"], inputs=[selected, b["skill_dd"]], outputs=fetch_outputs,
            show_progress="minimal", api_name=False,
        )

        # -- lens: one-way filters reframe the map + search choices --
        b["state_dd"].change(
            b["state_regions"], inputs=b["state_dd"], outputs=b["region_dd"],
            api_name=False,
        ).then(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["search_dd"]], api_name=False,
        )
        b["region_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["search_dd"]], api_name=False,
        )
        # the Skill filter doubles as the scoring tier: refilter the map,
        # then rescore the picked spot's week at that level
        b["skill_dd"].change(
            b["filter_changed"], inputs=[b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=[b["map_plot"], b["search_dd"]], api_name=False,
        ).then(
            s["fetch_forecast"], inputs=[selected, b["skill_dd"]], outputs=fetch_outputs,
            show_progress="minimal", api_name=False,
        )
        # -- picking a spot re-tells the page, then auto-fetches its week --
        b["search_dd"].change(
            b["pick_by_name"],
            inputs=[b["search_dd"], b["state_dd"], b["region_dd"], b["skill_dd"]],
            outputs=select_outputs, api_name=False,
        ).then(
            s["fetch_forecast"], inputs=[selected, b["skill_dd"]], outputs=fetch_outputs,
            show_progress="minimal", api_name=False,
        )
        # -- intel rail: pill tabs swap the three feature columns --
        i["tab_picker"].change(i["pick"], inputs=i["tab_picker"],
                               outputs=[i["report_col"], i["world_col"], i["climate_col"]],
                               api_name=False)
        # the report button lives in the intel rail; its handler stays story-side
        i["narrate_btn"].click(s["narrate"], inputs=scored, outputs=i["report_md"],
                               show_progress="minimal", api_name=False)
        # -- agent: chat streams trace cards + meter + verdict + charts --
        chat_inputs = [a["msg"], a["chatbot"], b["skill_dd"], a["token_box"],
                       selected, agent_store, a["steps_slider"], a["state_dd"],
                       a["region_dd"]]
        a["send_btn"].click(
            a["chat"], inputs=chat_inputs, outputs=agent_outputs,
            show_progress="minimal", api_name=False,
        )
        a["msg"].submit(
            a["chat"], inputs=chat_inputs, outputs=agent_outputs,
            show_progress="minimal", api_name=False,
        )
        a["spot_dd"].change(
            a["show_spot"], inputs=[a["spot_dd"], agent_store],
            outputs=[a["agent_strip"]], api_name=False,
        )
        a["clear_btn"].click(a["clear"], inputs=None, outputs=agent_outputs,
                             api_name=False)
        # Chips fill AND send in one click (set msg, then run the chat chain).
        for chip, prompt in zip(a["chips"], agent_panel.CHIP_PROMPTS):
            chip.click(a["chip_text"](prompt), inputs=None, outputs=[a["msg"]],
                       api_name=False).then(
                a["chat"], inputs=chat_inputs, outputs=agent_outputs,
                show_progress="minimal", api_name=False,
            )
        # -- agent filters: page-one pattern, State rewrites Region choices --
        a["state_dd"].change(
            a["state_regions"], inputs=a["state_dd"], outputs=a["region_dd"],
            api_name=False,
        )
        # -- agent context line: what the bar inherits from the page --
        ctx_outputs = [a["ctx_md"]]
        ctx_inputs = [b["skill_dd"], selected, a["steps_slider"],
                      a["state_dd"], a["region_dd"]]
        for trigger in (selected, b["skill_dd"], a["steps_slider"],
                        a["state_dd"], a["region_dd"]):
            trigger.change(
                a["ctx"], inputs=ctx_inputs,
                outputs=ctx_outputs, api_name=False,
            )

    return demo
