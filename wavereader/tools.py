"""Agent tools: the function schemas handed to the LLM.

Tools are thin wrappers over spots.py / forecasts.py / scoring.py — the
model chooses them, the deterministic modules compute the values.
"""

from __future__ import annotations

from wavereader import forecasts, scoring, spots

TOOL_SCHEMAS = (
    "get_forecast",
    "score_week",
    "find_spots",
    "get_spot_knowledge",
    "rank_spots_this_week",
)


def get_forecast(spot_name: str, region: str) -> dict:
    """Hourly marine + wind forecast for a named spot."""
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)


def score_week(spot_name: str, region: str) -> list[dict]:
    """Hour-by-hour surf scores for the next 7 days at a spot."""
    s = spots.get_spot(spot_name, region)
    if s is None:
        return []
    forecast = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)
    return scoring.score_week(forecast, s.model_dump())


def find_spots(query: str = "", skill: str | None = None, limit: int = 10) -> list[dict]:
    """Search breaks by name/region with optional skill filter."""
    results = spots.find_spots(query=query, skill=skill, limit=limit)
    return [b.model_dump() for b in results]


def get_spot_knowledge(spot_name: str, region: str) -> dict:
    """Knowledge-base profile for a spot (ideal swell/wind/tide)."""
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return s.model_dump()


def rank_spots_this_week(region: str, skill: str | None = None) -> list[dict]:
    """Rank spots in a region by their best score this week."""
    spots_list = spots.find_spots(region=region, skill=skill)
    if not spots_list:
        return []
    forecasts_map: dict[tuple[str, str], dict] = {}
    for b in spots_list:
        d = forecasts.get_forecast(b.coordinates.lat, b.coordinates.lng)
        forecasts_map[(b.name, b.region)] = d
    return scoring.rank_spots_this_week(
        forecasts_map,
        [b.model_dump() for b in spots_list],
    )