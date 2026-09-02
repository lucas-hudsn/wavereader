"""smolagents CodeAgent for surf forecasting.

Provider-agnostic: uses InferenceClientModel with base URL + key from env
(``HF_TOKEN`` -> https://router.huggingface.co/v1,
``NVIDIA_API_KEY`` -> https://integrate.api.nvidia.com/v1). Default model:
``Qwen/Qwen3-Next-80B-A3B-Instruct`` (only tested model supporting both
OpenAI-style tool calling and strict ``json_schema`` on the HF router — see
``data/GENERATION.md`` before swapping models).

The agent interprets and explains only; all numbers come from scoring.py /
forecasts.py via the tools in tools.py. Streaming + trace capture feed the UI
trace panel; the UI renders charts itself from the trace (the agent never
needs to plot).
"""

from __future__ import annotations

import importlib.resources
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Generator

import yaml
from smolagents import CodeAgent, InferenceClientModel, OpenAIServerModel, PromptTemplates, Tool
from smolagents.agents import ToolOutput
from smolagents.memory import FinalAnswerStep, ToolCall as SmolToolCall
from smolagents.models import ChatMessageStreamDelta

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
5. Always cite the data source (tool name) when giving numbers.
6. Be concise and practical — surfers want actionable recommendations.
7. The UI renders charts automatically whenever you surface forecast or score data — never describe plots or say you cannot show them.

CALL TOOLS EXACTLY LIKE THIS (keyword spellings matter):
- find_spots(query="QLD", skill="beginner")  # query = spot name OR state code: NSW, QLD, VIC, WA, SA, TAS
- get_spot_knowledge(spot_name="Snapper Rocks", region="QLD")
- get_forecast(spot_name="Snapper Rocks", region="QLD")
- score_week(spot_name="Snapper Rocks", region="QLD")  # ONE spot per call
- rank_spots_this_week(region="QLD", skill="beginner")  # use this to COMPARE many spots in a state

Workflow: to answer "where should I surf in <state>", call rank_spots_this_week first,
then get_spot_knowledge + score_week for the top 1-2 spots. Never invent keyword
names — use exactly the ones above.
"""

PROVIDER_HF = "hf"
PROVIDER_NIM = "nim"

DEFAULT_MODEL = "Qwen/Qwen3-Next-80B-A3B-Instruct"
HF_BASE_URL = "https://router.huggingface.co/v1"
NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


@dataclass
class TraceEvent:
    """A single event in the agent trace."""

    type: str  # "tool_call", "tool_result", "llm_chunk", "final_answer", "error"
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
        self.events.append(
            TraceEvent(type=event_type, timestamp=time.time(), data=data)
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "question": self.question,
                "model": self.model,
                "provider": self.provider,
                "events": [
                    {"type": e.type, "timestamp": e.timestamp, "data": e.data}
                    for e in self.events
                ],
            }
        )


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
    description = (
        "Get hour-by-hour surf scores for the next 7 days at ONE spot. "
        "Example: score_week(spot_name=\"Snapper Rocks\", region=\"QLD\"). "
        "To compare many spots, use rank_spots_this_week instead."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "Australian state/region"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> list[dict]:
        return score_week(spot_name, region)


class FindSpotsTool(Tool):
    name = "find_spots"
    description = (
        "Search breaks by name or state code with optional skill filter. "
        "Example: find_spots(query=\"QLD\", skill=\"beginner\")"
    )
    inputs = {
        "query": {"type": "string", "description": "Spot name OR Australian state code (NSW, QLD, VIC, WA, SA, TAS)", "nullable": True},
        "region": {"type": "string", "description": "Alias for query when searching a state code", "nullable": True},
        "skill": {"type": "string", "description": "Skill level filter (beginner, intermediate, advanced, expert)", "nullable": True},
        "limit": {"type": "integer", "description": "Maximum number of results to return", "nullable": True},
    }
    output_type = "object"

    def forward(
        self,
        query: str = "",
        region: str | None = None,
        skill: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        return find_spots(query=query or region or "", skill=skill, limit=limit)


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
    description = (
        "Rank ALL spots in a state by their best score this week. "
        "Example: rank_spots_this_week(region=\"QLD\", skill=\"beginner\"). "
        "Use this first for 'where should I surf' questions."
    )
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


def _build_model(provider: str, model: str | None = None) -> OpenAIServerModel:
    """Build the OpenAI-compatible model client for the given provider.

    Both the HF router and NVIDIA NIM speak the OpenAI chat-completions
    protocol, so one client class covers the HF⇄NIM switch.
    """
    model_id = model or DEFAULT_MODEL

    if provider == PROVIDER_HF:
        token = os.getenv("HF_TOKEN")
        if not token:
            raise ValueError(
                "HF_TOKEN environment variable not set for Hugging Face provider"
            )
        return OpenAIServerModel(
            model_id=model_id,
            api_base=HF_BASE_URL,
            api_key=token,
        )
    elif provider == PROVIDER_NIM:
        api_key = os.getenv("NVIDIA_API_KEY")
        if not api_key:
            raise ValueError(
                "NVIDIA_API_KEY environment variable not set for NVIDIA NIM provider"
            )
        return OpenAIServerModel(
            model_id=model_id,
            api_base=NIM_BASE_URL,
            api_key=api_key,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'hf' or 'nim'")


def _detect_provider() -> str:
    """Auto-detect provider from available env vars (NIM preferred)."""
    if os.getenv("NVIDIA_API_KEY"):
        return PROVIDER_NIM
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
        # Load smolagents' default prompt templates, then override system prompt
        default_templates_yaml = (
            importlib.resources.files("smolagents.prompts")
            .joinpath("code_agent.yaml")
            .read_text()
        )
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

    def _capture_item(self, item: Any) -> bool:
        """Record a tool_call/tool_result from a smolagents stream item.

        Returns True if the item was consumed as a tool event.
        """
        if self._trace is None:
            return False
        if isinstance(item, SmolToolCall):
            self._trace.add_event(
                "tool_call",
                {"name": item.name, "arguments": item.arguments, "id": item.id},
            )
            return True
        if isinstance(item, ToolOutput):
            name = item.tool_call.name if item.tool_call is not None else None
            self._trace.add_event(
                "tool_result",
                {"name": name, "observation": str(item.observation)},
            )
            return True
        return False

    def _traced_step_stream(self, original_step_stream):
        """Wrap a _step_stream generator so run() also captures tool events."""

        def traced(memory_step, *args, **kwargs):
            for item in original_step_stream(memory_step, *args, **kwargs):
                self._capture_item(item)
                yield item

        return traced

    def run(self, question: str) -> str:
        """Run the agent synchronously and return the final answer."""
        self._trace = AgentTrace(
            question=question, model=self.model, provider=self.provider
        )
        original_step_stream = self._agent._step_stream
        self._agent._step_stream = self._traced_step_stream(original_step_stream)
        try:
            return self._agent.run(question)
        finally:
            self._agent._step_stream = original_step_stream

    def run_stream(
        self, question: str
    ) -> Generator[tuple[str, Any], None, None]:
        """Run the agent with streaming.

        Yields ("model", delta) for LLM tokens, ("tool", tool_name) when a
        tool call fires, and ("final", answer) at the end. Tool activity is
        captured into the trace from the stream itself.
        """
        self._trace = AgentTrace(
            question=question, model=self.model, provider=self.provider
        )
        for item in self._agent.run(question, stream=True):
            if isinstance(item, ChatMessageStreamDelta):
                if item.content:
                    self._trace.add_event("llm_chunk", {"chunk": item.content})
                    yield ("model", item.content)
                continue
            if isinstance(item, FinalAnswerStep):
                self._trace.add_event("final_answer", {"answer": item.output})
                yield ("final", item.output)
                continue
            if self._capture_item(item) and isinstance(item, SmolToolCall):
                name = item.name if isinstance(item.name, str) else "code action"
                yield ("tool", name)


def run_agent(
    question: str, provider: str | None = None, model: str | None = None
) -> str:
    """Run the surf agent and return the answer."""
    agent = SurfAgent(provider=provider, model=model)
    return agent.run(question)


def run_agent_stream(
    question: str, provider: str | None = None, model: str | None = None
):
    """Run the surf agent with streaming."""
    agent = SurfAgent(provider=provider, model=model)
    yield from agent.run_stream(question)


if __name__ == "__main__":
    import sys

    question = (
        " ".join(sys.argv[1:])
        if len(sys.argv) > 1
        else "What time should I surf Snapper Rocks today?"
    )
    print(f"Question: {question}\n")
    print("Answer:")
    for kind, chunk in run_agent_stream(question):
        if kind == "model":
            print(chunk, end="", flush=True)
        elif kind == "tool":
            print(f"\n[tool: {chunk}]", flush=True)
    print()
