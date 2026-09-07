"""smolagents CodeAgent for surf forecasting.

HF-only: uses OpenAIServerModel via the Hugging Face Router
(https://router.huggingface.co/v1) with an HF_TOKEN. Default model is
``nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16`` (NVIDIA Nemotron 3.5).
The token can be supplied via env (HF_TOKEN) or per-session from the Gradio
UI (passed as hf_token).

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
- score_week(spot_name="Snapper Rocks", region="QLD", skill="intermediate")  # ONE spot per call
- rank_spots_this_week(region="QLD", skill="beginner")  # use this to COMPARE many spots in a state

Workflow: to answer "where should I surf in <state>", call rank_spots_this_week first,
then get_spot_knowledge + score_week for the top 1-2 spots. Never invent keyword
names — use exactly the ones above.
"""

PROVIDER_HF = "hf"
PROVIDER_NIM = "nim"  # compat shim (deprecated — HF-only now)
# Primary: Nemotron 3.5 Lightning (user requested). NOTE: as of 2026-09-06 this
# model page shows "This model isn't deployed by any Inference Provider" for
# HF Inference Providers — HF Router will return
# `invalid_request_error: not supported by any provider you have enabled`.
# Fallback below (Nano-8B via Featherless AI) IS deployed and keeps the
# NVIDIA track, so unsupported-model errors auto-fallback via _is_unsupported_model_error.
HF_DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16"
HF_FALLBACK_MODEL = "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
# Kept for explicit user requests / compat — will auto-fallback if unsupported.
HF_70B_MODEL = "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF"
HF_NANO_MODEL = "nvidia/Llama-3.1-Nemotron-Nano-8B-v1"
NIM_DEFAULT_MODEL = HF_DEFAULT_MODEL  # compat
DEFAULT_MODEL = HF_DEFAULT_MODEL
HF_BASE_URL = "https://router.huggingface.co/v1"
NIM_BASE_URL = HF_BASE_URL  # compat

PROVIDER_MODELS = {
    PROVIDER_HF: HF_DEFAULT_MODEL,
    PROVIDER_NIM: NIM_DEFAULT_MODEL,
}


def get_default_model(provider: str | None = None) -> str:
    """Return the default HF model (provider arg kept for compat)."""
    if provider and provider in PROVIDER_MODELS:
        return PROVIDER_MODELS[provider]
    return HF_DEFAULT_MODEL


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
        "Example: score_week(spot_name=\"Snapper Rocks\", region=\"QLD\", skill=\"intermediate\"). "
        "To compare many spots, use rank_spots_this_week instead."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "Australian state/region"},
        "skill": {"type": "string", "description": "Surfer skill level (beginner, intermediate, advanced, expert)", "nullable": True},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str, skill: str | None = None) -> list[dict]:
        return score_week(spot_name, region, skill=skill)


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


def _build_model(
    provider: str | None = None,
    model: str | None = None,
    hf_token: str | None = None,
) -> OpenAIServerModel:
    """Build the HF Router model client.

    Token priority: explicit hf_token arg > HF_TOKEN env var.
    NIM provider is a compat shim that also uses the HF Router.
    """
    model_id = model or get_default_model(provider)
    # compat: if provider == nim, still require HF token but message mentions both for old tests
    token = (hf_token or "").strip() or os.getenv("HF_TOKEN") or os.getenv("NVIDIA_API_KEY") or ""
    if not token:
        if provider == PROVIDER_NIM:
            raise ValueError(
                "HF_TOKEN (or NVIDIA_API_KEY compat) not set — enter your Hugging Face token in the UI "
                "or set HF_TOKEN (https://huggingface.co/settings/tokens). NVIDIA_API_KEY is deprecated."
            )
        raise ValueError(
            "HF_TOKEN not set — enter your Hugging Face token in the UI or set HF_TOKEN in your environment "
            "(https://huggingface.co/settings/tokens). The token is used for the HF Router (Nemotron)."
        )
    return OpenAIServerModel(
        model_id=model_id,
        api_base=HF_BASE_URL,
        api_key=token,
    )


def _is_unsupported_model_error(exc: Exception) -> bool:
    """Check if exception is the HF Router 'not supported by any provider' error."""
    msg = str(exc).lower()
    return "not supported by any provider" in msg or "is not supported by any provider" in msg


def _detect_provider() -> str:
    """Auto-detect (compat): prefers NIM if NVIDIA_API_KEY present, else HF. NIM is deprecated shim."""
    if os.getenv("NVIDIA_API_KEY"):
        return PROVIDER_NIM
    return PROVIDER_HF


class SurfAgent:
    """Surf forecasting agent with streaming and trace capture."""

    def __init__(
        self,
        provider: str | None = None,
        model: str | None = None,
        hf_token: str | None = None,
    ):
        # provider is kept for compat (hf preferred, nim shim maps to hf)
        self.provider = provider or _detect_provider()
        if self.provider not in PROVIDER_MODELS:
            raise ValueError(f"Unknown provider: {self.provider}. Use 'hf' or 'nim' (nim is deprecated, use hf)")
        self.model = model or get_default_model(self.provider)
        self._hf_token = hf_token  # stored for fallback rebuild
        if hf_token is not None:
            self._model = _build_model(self.provider, self.model, hf_token=hf_token)
        else:
            self._model = _build_model(self.provider, self.model)
        # Load smolagents' default prompt templates, then append system prompt
        default_templates_yaml = (
            importlib.resources.files("smolagents.prompts")
            .joinpath("code_agent.yaml")
            .read_text()
        )
        default_templates = yaml.safe_load(default_templates_yaml)
        default_templates["system_prompt"] += "\n\n" + SYSTEM_PROMPT
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

    def _rebuild_with_fallback(self, hf_token: str | None = None) -> None:
        """Rebuild internal model/agent with the fallback (Nano) model after unsupported-model error."""
        self.model = HF_FALLBACK_MODEL
        # _build_model reads HF_TOKEN env; pass explicit token if we have one stored
        token = hf_token if hf_token is not None else getattr(self, "_hf_token", None)
        self._model = _build_model(self.provider, self.model, hf_token=token)
        default_templates_yaml = (
            importlib.resources.files("smolagents.prompts")
            .joinpath("code_agent.yaml")
            .read_text()
        )
        default_templates = yaml.safe_load(default_templates_yaml)
        default_templates["system_prompt"] += "\n\n" + SYSTEM_PROMPT
        prompt_templates = PromptTemplates(**default_templates)
        self._agent = CodeAgent(
            tools=TOOLS,
            model=self._model,
            prompt_templates=prompt_templates,
            max_steps=10,
        )
        if self._trace is not None:
            self._trace.model = self.model

    def run(self, question: str) -> str:
        """Run the agent synchronously and return the final answer."""
        self._trace = AgentTrace(
            question=question, model=self.model, provider=self.provider
        )
        original_step_stream = self._agent._step_stream
        self._agent._step_stream = self._traced_step_stream(original_step_stream)
        try:
            try:
                return self._agent.run(question)
            except Exception as exc:
                if _is_unsupported_model_error(exc) and self.model != HF_FALLBACK_MODEL:
                    self._rebuild_with_fallback()
                    return self._agent.run(question)
                raise
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
        try:
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
        except Exception as exc:
            if _is_unsupported_model_error(exc) and self.model != HF_FALLBACK_MODEL:
                self._rebuild_with_fallback()
                yield from self.run_stream(question)
                return
            raise


def run_agent(
    question: str,
    provider: str | None = None,
    model: str | None = None,
    hf_token: str | None = None,
) -> str:
    """Run the surf agent and return the answer."""
    agent = SurfAgent(provider=provider, model=model, hf_token=hf_token)
    return agent.run(question)


def run_agent_stream(
    question: str,
    provider: str | None = None,
    model: str | None = None,
    hf_token: str | None = None,
):
    """Run the surf agent with streaming."""
    agent = SurfAgent(provider=provider, model=model, hf_token=hf_token)
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
