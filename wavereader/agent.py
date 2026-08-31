"""smolagents CodeAgent for surf forecasting.

Provider-agnostic: uses InferenceClientModel with base URL + key from env
(``HF_TOKEN`` -> https://router.huggingface.co/v1,
``NVIDIA_API_KEY`` -> https://integrate.api.nvidia.com/v1). Default model:
``Qwen/Qwen3-Next-80B-A3B-Instruct`` (only tested model supporting both
OpenAI-style tool calling and strict ``json_schema`` on the HF router — see
``data/GENERATION.md`` before swapping models).

The agent interprets and explains only; all numbers come from scoring.py /
forecasts.py via the tools in tools.py. Streaming + trace capture for the UI
trace panel.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from smolagents import CodeAgent, InferenceClientModel, PromptTemplates, Tool, tool
import yaml
import importlib.resources

from wavereader import forecasts, scoring, spots
from wavereader.tools import (
    find_spots,
    get_forecast,
    get_spot_knowledge,
    rank_spots_this_week,
    score_week,
)

SYSTEM_PROMPT = """You are a surf forecasting assistant for Australian breaks.

IMPORTANT RULES:
1. You NEVER compute scores, forecasts, or rankings yourself. All numbers MUST come from the provided tools.
2. You interpret and explain the data returned by tools. You do not invent wave heights, wind speeds, or surf scores.
3. Tide information is qualitative only (from the knowledge base). Open-Meteo does not provide tides — never promise tide curves.
4. When the user asks about a specific spot, use get_spot_knowledge first to understand its ideal conditions.
5. For forecasts and scores, use get_forecast and score_week. For rankings, use rank_spots_this_week.
6. For finding spots by region/skill, use find_spots.
7. Always cite the data source (tool name) when giving numbers.
8. Be concise and practical — surfers want actionable recommendations.
"""

PROVIDER_HF = "hf"
PROVIDER_NIM = "nim"

DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
HF_BASE_URL = "https://router.huggingface.co/v1"
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


@dataclass
class TraceEvent:
    """A single event in the agent trace."""
    type: str  # "tool_call", "tool_result", "llm_chunk", "error"
    timestamp: float
    data: dict[str, Any]


@dataclass
class AgentTrace:
    """Captured trace of an agent run."""
    events: list[TraceEvent] = field(default_factory=list)
    question: str = ""
    model: str = ""
    provider: str = ""

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        import time
        self.events.append(TraceEvent(type=event_type, timestamp=time.time(), data=data))

    def to_json(self) -> str:
        return json.dumps({
            "question": self.question,
            "model": self.model,
            "provider": self.provider,
            "events": [
                {"type": e.type, "timestamp": e.timestamp, "data": e.data}
                for e in self.events
            ]
        })


class GetForecastTool(Tool):
    name = "get_forecast"
    description = "Get hourly marine + wind forecast for a named spot."
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot (e.g., 'Snapper Rocks')"},
        "region": {"type": "string", "description": "Australian state/region (NSW, QLD, VIC, WA, SA, TAS)"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_forecast(spot_name, region)


class ScoreWeekTool(Tool):
    name = "score_week"
    description = "Get hour-by-hour surf scores for the next 7 days at a spot."
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "Australian state/region"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> list[dict]:
        return score_week(spot_name, region)


class FindSpotsTool(Tool):
    name = "find_spots"
    description = "Search breaks by name/region with optional skill filter."
    inputs = {
        "query": {"type": "string", "description": "Search query for spot name or region", "nullable": True},
        "skill": {"type": "string", "description": "Skill level filter (beginner, intermediate, advanced, expert)", "nullable": True},
        "limit": {"type": "integer", "description": "Maximum number of results to return", "nullable": True},
    }
    output_type = "object"

    def forward(self, query: str = "", skill: str | None = None, limit: int = 10) -> list[dict]:
        return find_spots(query=query, skill=skill, limit=limit)


class GetSpotKnowledgeTool(Tool):
    name = "get_spot_knowledge"
    description = "Get knowledge-base profile for a spot (ideal swell/wind/tide, skill level, hazards)."
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "Australian state/region"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_spot_knowledge(spot_name, region)


class RankSpotsThisWeekTool(Tool):
    name = "rank_spots_this_week"
    description = "Rank spots in a region by their best score this week, with optional skill filter."
    inputs = {
        "region": {"type": "string", "description": "Australian state/region"},
        "skill": {"type": "string", "description": "Skill level filter", "nullable": True},
    }
    output_type = "object"

    def forward(self, region: str, skill: str | None = None) -> list[dict]:
        return rank_spots_this_week(region, skill)


TOOLS = [
    GetForecastTool(),
    ScoreWeekTool(),
    FindSpotsTool(),
    GetSpotKnowledgeTool(),
    RankSpotsThisWeekTool(),
]


def _build_model(provider: str, model: str | None = None) -> InferenceClientModel:
    """Build the InferenceClientModel for the given provider."""
    model_id = model or DEFAULT_MODEL

    if provider == PROVIDER_HF:
        token = os.getenv("HF_TOKEN")
        if not token:
            raise ValueError("HF_TOKEN environment variable not set for Hugging Face provider")
        return InferenceClientModel(
            model_id=model_id,
            api_base=HF_BASE_URL,
            token=token,
        )
    elif provider == PROVIDER_NIM:
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError("NVIDIA_API_KEY environment variable not set for NVIDIA NIM provider")
        return InferenceClientModel(
            model_id=model_id,
            api_base=NIM_BASE_URL,
            token=api_key,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'hf' or 'nim'")


def _detect_provider() -> str:
    """Auto-detect provider from available env vars."""
    if os.getenv("NVIDIA_API_KEY"):
        return PROVIDER_NIM
    if os.getenv("HF_TOKEN"):
        return PROVIDER_HF
    return PROVIDER_HF


class SurfAgent:
    """Surf forecasting agent with streaming and trace capture."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
    ):
        self.provider = provider or _detect_provider()
        self.model = model or DEFAULT_MODEL
        self._model = _build_model(self.provider, self.model)
        # Load default prompt templates from smolagents package
        default_templates_yaml = importlib.resources.files("smolagents.prompts").joinpath("code_agent.yaml").read_text()
        default_templates = yaml.safe_load(default_templates_yaml)
        default_templates["system_prompt"] = SYSTEM_PROMPT
        prompt_templates = PromptTemplates(**default_templates)
        self._agent = CodeAgent(
            tools=TOOLS,
            model=self._model,
            prompt_templates=prompt_templates,
            max_steps=10,
        )
        self._trace: AgentTrace | None = None

    @property
    def trace(self) -> AgentTrace | None:
        return self._trace

    def run(self, question: str) -> str:
        """Run the agent synchronously and return the final answer."""
        self._trace = AgentTrace(question=question, model=self.model, provider=self.provider)
        return self._agent.run(question)

    def run_stream(self, question: str):
        """Run the agent with streaming, yielding (chunk, trace_event) pairs."""
        self._trace = AgentTrace(question=question, model=self.model, provider=self.provider)

        # Wrap the agent's run to capture trace events
        from smolagents.agents import MultiStepAgent
        from smolagents.memory import ActionStep

        original_step = self._agent.step

        def traced_step(memory_step: ActionStep, *args, **kwargs):
            # Capture tool calls
            if memory_step.tool_calls:
                for tc in memory_step.tool_calls:
                    self._trace.add_event("tool_call", {
                        "name": tc.name,
                        "arguments": tc.arguments,
                        "id": tc.id,
                    })
            # Capture tool results
            if memory_step.observations:
                for obs in memory_step.observations:
                    self._trace.add_event("tool_result", {"observation": str(obs)})
            return original_step(memory_step, *args, **kwargs)

        self._agent.step = traced_step

        try:
            for chunk in self._agent.run(question, stream=True):
                if self._trace:
                    self._trace.add_event("llm_chunk", {"chunk": str(chunk)})
                yield chunk
        finally:
            self._agent.step = original_step


def run_agent(question: str, provider: str | None = None, model: str | None = None) -> str:
    """Run the surf agent and return the answer."""
    agent = SurfAgent(provider=provider, model=model)
    return agent.run(question)


def run_agent_stream(question: str, provider: str | None = None, model: str | None = None):
    """Run the surf agent with streaming."""
    agent = SurfAgent(provider=provider, model=model)
    yield from agent.run_stream(question)


if __name__ == "__main__":
    import sys
    question = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What time should I surf Snapper Rocks today?"
    print(f"Question: {question}\n")
    print("Answer:")
    for chunk in run_agent_stream(question):
        print(chunk, end="", flush=True)
    print()