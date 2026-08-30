"""Deterministic surf-quality scoring.

The LLM never owns numbers: every score and ranking comes from here.
Produces a 0-10 quality score per hour plus a component breakdown
(swell size vs ideal, period, wind strength/direction vs offshore, tide is
qualitative only — Open-Meteo has no tides, so it comes from the knowledge
base and never feeds the numeric score).
"""

from __future__ import annotations


def score_hour(
    wave_height_m: float,
    wave_period_s: float,
    wind_speed_kt: float,
    wind_direction_deg: float,
    spot: dict,
) -> dict:
    """Score one hour against a spot's ideal profile.

    TODO: component subscores (swell size, period, wind strength,
    wind alignment vs ideal direction) weighted into a 0-10 total plus a
    breakdown dict for the UI.
    """
    raise NotImplementedError


def score_week(forecast: dict, spot: dict) -> list[dict]:
    """Score every hour of a 7-day forecast for one spot.

    TODO: map score_hour over the merged hourly frame.
    """
    raise NotImplementedError
