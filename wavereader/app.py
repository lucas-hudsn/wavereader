"""Gradio demo UI.

Home page is a map of Australia (select your break), plus chat with the
agent, interactive seaborn-styled charts (plotly/altair aesthetics) rendered
whenever the agent surfaces forecast/wind data, and the agent trace panel.
Calls the core modules (and FastAPI endpoints) — no custom frontend this
week.
"""

from __future__ import annotations


def build_ui() -> object:
    """Assemble the Blocks demo (map home, chat, charts, trace panel).

    TODO: Australia map home page, chat pipeline against agent.run_agent,
    chart rendering, trace panel.
    """
    raise NotImplementedError


if __name__ == "__main__":
    demo = build_ui()
    demo.launch()
