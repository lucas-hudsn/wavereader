"""Shared constants + paths for the wave~reader front end."""

from __future__ import annotations

from pathlib import Path

DATA_PATH = Path(__file__).parent.parent.parent / "data" / "australia-surf-breaks-enriched.json"

ALL = "All"


SKILL_ORDER = ["beginner", "intermediate", "advanced", "expert", "pro-only"]


SKILL_COLORS = {
    "beginner": "#2ca02c",
    "intermediate": "#1f77b4",
    "advanced": "#ff7f0e",
    "expert": "#d62728",
    "pro-only": "#9467bd",
}


CUSTOM_MARKER_COLOR = "#FFD700"


_NO_BREAK_HEADER = "### No break selected — pick one in the break book tab."


_NO_REPORT_MD = "_No report yet — pick a break to auto-load the forecast, then generate the report._"


SCORE_EXPLAINER_MD = (
    "**0–10 = 30% size · 20% direction · 30% wind · 20% period**"
    " (missing direction → weight shared).\n"
    "\n"
    "| component | rule |\n"
    "|---|---|\n"
    "| swell size 30% | 10 in ideal ft range, gaussian outside × skill cap |\n"
    "| direction 20% | gaussian from ideal (~45° tol.) |\n"
    "| wind 30% | (speed+dir)/2; ≤5kt=10, 0 above limit; offshore→onshore; gusts −1/−2 |\n"
    "| period 20% | 0 <4s → 10 @14s; beginners ease >12s |\n"
    "\n"
    "red→green bars; ★ = best hour. deterministic in `app/scoring.py`."
)


BROWSE_INTRO = (
    "a guide to australian surf breaks — browse 238 breaks on the **break book** page, "
    "then score the week ahead + get an ai write-up on the **swell check** page, "
    "or switch to **agentic mode** above to chat with the surf agent."
)


AGENT_INTRO = (
    "agentic mode — chat with the surf agent below. "
    "charts + leaderboard stay hidden until the agent actually scores a spot."
)


AGENT_MODE_LABEL = "agentic mode"


AUSTRALIA_CENTER = {"lat": -25.5, "lon": 134.0}


AUSTRALIA_ZOOM = 3.5


HISTORY_PREPEND_TURNS = 6
