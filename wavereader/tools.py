"""Agent tools: the function schemas handed to the LLM.

Tools are thin wrappers over spots.py / forecasts.py / scoring.py — the
model chooses them, the deterministic modules compute the values.
"""

from __future__ import annotations

TOOL_SCHEMAS = (
    "get_forecast",
    "score_week",
    "find_spots",
    "get_spot_knowledge",
    "rank_spots_this_week",
)


def get_forecast(spot: str) -> dict:
    """Hourly marine + wind forecast for a named spot. TODO."""
    raise NotImplementedError


def score_week(spot: str) -> dict:
    """Hour-by-hour surf scores for the next 7 days at a spot. TODO."""
    raise NotImplementedError


def find_spots(query: str, skill: str | None = None) -> list[dict]:
    """Search breaks by name/region with optional skill filter. TODO."""
    raise NotImplementedError


def get_spot_knowledge(spot: str) -> dict:
    """Knowledge-base profile for a spot (ideal swell/wind/tide). TODO."""
    raise NotImplementedError


def rank_spots_this_week(region: str, skill: str | None = None) -> list[dict]:
    """Rank spots in a region by their best score this week. TODO."""
    raise NotImplementedError
