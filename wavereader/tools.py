"""Agent tools: forecast/score/knowledge lookups for surf forecasting.

Plain functions resolve a spot by ``(name, region)`` and delegate to
``forecasts``/``scoring``/``spots``; the smolagents ``Tool`` subclasses below
expose them to the CodeAgent. The LLM never computes numbers itself.
"""

from __future__ import annotations

from smolagents import Tool
from wavereader import forecasts, scoring, spots


def _normalize_skill(skill: str | None) -> str:
    """Normalize user/agent skill query to canonical tier in scoring.SKILL_LEVELS."""
    if not skill:
        return "intermediate"
    s = skill.lower().strip()
    if "beg" in s:
        return "beginner"
    if "exp" in s or "pro" in s or "elite" in s:
        return "expert"
    if "adv" in s:
        return "advanced"
    if "inter" in s:
        return "intermediate"
    return "intermediate"


def get_forecast(spot_name: str, region: str) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)


def score_week(
    spot_name: str, region: str, skill: str | None = None
) -> dict | list[dict]:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    forecast = forecasts.get_forecast(s.coordinates.lat, s.coordinates.lng)
    skill_level = _normalize_skill(skill)
    return scoring.score_week(forecast, s.model_dump(), skill_level=skill_level)


def find_spots(query: str = "", skill: str | None = None, limit: int = 10) -> list[dict]:
    results = spots.find_spots(query=query, skill=skill, limit=limit)
    return [b.model_dump() for b in results]


def get_spot_knowledge(spot_name: str, region: str) -> dict:
    s = spots.get_spot(spot_name, region)
    if s is None:
        return {"error": f"Spot '{spot_name}' ({region}) not found"}
    return s.model_dump()


def rank_spots_this_week(region: str, skill: str | None = None) -> list[dict]:
    spots_list = spots.find_spots(region=region, skill=skill)
    if not spots_list:
        return []
    forecasts_map = {}
    for b in spots_list:
        d = forecasts.get_forecast(b.coordinates.lat, b.coordinates.lng)
        forecasts_map[(b.name, b.region)] = d
    skill_level = _normalize_skill(skill)
    return scoring.rank_spots_this_week(
        forecasts_map,
        [b.model_dump() for b in spots_list],
        skill_level=skill_level,
    )


class GetForecastTool(Tool):
    name = "get_forecast"
    description = "Retrieve the wave forecast for a specific surf spot."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located (e.g., 'QLD').",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_forecast(spot_name=spot_name, region=region)


class ScoreWeekTool(Tool):
    name = "score_week"
    description = "Score the conditions of a surf spot for the upcoming week based on its forecast."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located.",
        },
        "skill": {
            "type": "string",
            "description": "Surfer skill level (beginner, intermediate, advanced, expert).",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, spot_name: str, region: str, skill: str | None = None
    ) -> dict | list[dict]:
        return score_week(spot_name=spot_name, region=region, skill=skill)


class FindSpotsTool(Tool):
    name = "find_spots"
    description = "Search for surf spots based on query, skill level, and limit."
    inputs = {
        "query": {
            "type": "string",
            "description": "Search query or region for surf spots. Use State code (e.g., 'QLD') or specific spot names.",
            "nullable": True,
        },
        "skill": {
            "type": "string",
            "description": "Skill level (e.g., beginner, intermediate, advanced).",
            "nullable": True,
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of spots to return.",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, query: str = "", skill: str | None = None, limit: int = 10
    ) -> list[dict]:
        return find_spots(query=query, skill=skill, limit=limit)


class GetSpotKnowledgeTool(Tool):
    name = "get_spot_knowledge"
    description = "Retrieve metadata and detailed knowledge for a specific surf spot."
    inputs = {
        "spot_name": {
            "type": "string",
            "description": "Name of the surf spot.",
        },
        "region": {
            "type": "string",
            "description": "Region or state code where the spot is located.",
        },
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_spot_knowledge(spot_name=spot_name, region=region)


class RankSpotsThisWeekTool(Tool):
    name = "rank_spots_this_week"
    description = "Rank spots in a region for the upcoming week based on scored surf conditions."
    inputs = {
        "region": {
            "type": "string",
            "description": "Region or state code to rank spots in (e.g., 'QLD').",
        },
        "skill": {
            "type": "string",
            "description": "Skill level filter (e.g., beginner, intermediate, advanced).",
            "nullable": True,
        },
    }
    output_type = "object"

    def forward(
        self, region: str, skill: str | None = None
    ) -> list[dict]:
        return rank_spots_this_week(region=region, skill=skill)