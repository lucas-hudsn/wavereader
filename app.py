"""wave~reader v2 — HF Space entrypoint.

Builds the single-page Gradio 6 UI and exposes the deterministic tool
functions as public API/MCP endpoints (typed inputs so the MCP schema is
valid). Launch with ``uv run python app.py``; the Space runs this file
with ``demo`` already built — no secrets are read or logged here (the
BYO token box in the agent panel is session-only, the Space secret is
the fallback).
"""

from __future__ import annotations

import gradio as gr

from ui import _compat as C
from ui.app import build
from ui.theme import APP_CSS


def score_week(spot_name: str, skill: str = "intermediate") -> dict:
    """Score the week ahead for one break (deterministic, 0–10 per hour).

    Returns the spot, skill, scored hourly rows, daily bests, and the single
    best window. Backs the swell-check charts, the agent, and the MCP server.
    """
    return C.api_score_week(spot_name=spot_name, skill=skill)


def rank_region_week(region: str, skill: str = "intermediate") -> dict:
    """Rank every break in a region this week (deterministic).

    Returns the region, skill, and rows of name/region/best_score/best_time
    sorted best-first. Backs the agent leaderboard and the MCP server.
    """
    return C.api_rank_region_week(region=region, skill=skill)


def explain_score(spot_name: str, skill: str = "intermediate", time: str = "") -> dict:
    """Explain one scored hour: score plus size/direction/wind/period parts.

    ``time`` is an hourly timestamp from a score_week payload (defaults to
    the best window). Backs the agent and the MCP server.
    """
    return C.api_explain_score(spot_name=spot_name, skill=skill, time=time)


demo = build()

with demo:
    gr.api(score_week)
    gr.api(rank_region_week)
    gr.api(explain_score)

if __name__ == "__main__":
    demo.launch(css=APP_CSS, mcp_server=True)
