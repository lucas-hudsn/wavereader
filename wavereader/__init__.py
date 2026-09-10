"""wavereader — pure-core surf forecasting package (typed, tested, no Gradio)."""

from wavereader.breaks import filter_breaks, load_breaks, resolve_break
from wavereader.openmeteo import get_forecast
from wavereader.scoring import (
    daily_summary,
    rank_spots,
    rank_spots_this_week,
    score_hour,
    score_week,
)
from wavereader.seafloor import get_seafloor

__all__ = [
    "load_breaks",
    "resolve_break",
    "filter_breaks",
    "get_forecast",
    "score_hour",
    "score_week",
    "daily_summary",
    "rank_spots",
    "rank_spots_this_week",
    "get_seafloor",
]
