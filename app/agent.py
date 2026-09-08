"""smolagents CodeAgent for surf forecasting.

Single-model stack: Hugging Face Inference Providers via ``InferenceClientModel``
with ``PROVIDER = "deepinfra"`` and ``HF_DEFAULT_MODEL``. Token via
``hf_token`` arg or ``HF_TOKEN`` env.

Deterministic-numbers contract: the agent interprets and explains only; all
numbers come from app/scoring.py / app/forecasts.py via app/agent_tools.py.
Streaming + trace capture feed the UI trace panel; the UI renders charts
itself from the trace (the agent never plots).
"""

from __future__ import annotations

import importlib.resources
import inspect
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Generator

import yaml
from smolagents import CodeAgent, InferenceClientModel, PromptTemplates, Tool
from smolagents.agents import ActionOutput, ToolOutput
from smolagents.memory import ActionStep, FinalAnswerStep, ToolCall as SmolToolCall
from smolagents.models import ChatMessageStreamDelta

from app.agent_tools import (
    explain_score_breakdown,
    find_best_windows,
    find_similar_spots,
    find_spots,
    get_forecast,
    get_spot_knowledge,
    get_spot_sun_sst,
    list_states_regions,
    rank_spots_this_week,
    score_week,
)

SYSTEM_PROMPT = """You are a surf forecasting assistant for Australian breaks.

DATA LAYER: breaks live in data/australia-surf-breaks-enriched.json.
States are full names — New South Wales, Victoria, Queensland, Western
Australia, South Australia, Tasmania — with codes NSW/QLD/VIC/WA/SA/TAS
accepted as aliases. The `region` tool param takes a full state name OR a
sub-region (e.g. Central Coast). Skill tiers:
beginner/intermediate/advanced/expert/pro-only.

IMPORTANT RULES:
1. You NEVER compute scores, forecasts, or rankings yourself. All numbers MUST come from the provided tools.
2. You interpret and explain the data returned by tools. You do not invent wave heights, wind speeds, or surf scores.
3. Tide information is qualitative only (from the knowledge base). Open-Meteo does not provide tides — never promise tide curves.
4. When the user asks about a specific spot, use get_spot_knowledge first to understand its ideal conditions.
5. Always cite the data source (tool name) when giving numbers.
6. Be concise and practical — surfers want actionable recommendations.
7. The UI renders charts automatically whenever you surface forecast or score data — never describe plots or say you cannot show them.
8. Every spot you recommend MUST have a matching score_week call (preferred) or
   get_forecast call so its graphs appear below the chat. Never recommend a
   spot from memory/knowledge alone — score or fetch it first, then tell the
   user its swell + wind graphs are shown below.

CALL TOOLS EXACTLY LIKE THIS (keyword spellings matter):
- find_spots(query="Queensland", skill="beginner")  # query = spot name OR state name/code: Queensland/QLD, New South Wales/NSW, Victoria/VIC, Western Australia/WA, South Australia/SA, Tasmania/TAS
- list_states_regions()  # canonical state/region vocabulary — call when unsure of a spelling, never guess
- get_spot_knowledge(spot_name="Snapper Rocks", region="Queensland")
- get_forecast(spot_name="Snapper Rocks", region="Queensland")
- score_week(spot_name="Snapper Rocks", region="Queensland", skill="intermediate")  # ONE spot per call
- find_best_windows(spot_name="Snapper Rocks", region="Queensland", skill="intermediate", daypart="morning", weekend_only=False, min_score=6.0)  # daypart: morning/midday/afternoon/all — use for "mornings"/"weekend" questions, never do time math yourself
- explain_score_breakdown(spot_name="Snapper Rocks", region="Queensland", skill="intermediate")  # WHY an hour scored what it did — call before explaining components
- get_spot_sun_sst(spot_name="Snapper Rocks", region="Queensland")  # sunrise/sunset + sea temp + wetsuit hint (Open-Meteo frame)
- find_similar_spots(spot_name="Snapper Rocks", region="Queensland", limit=5)  # "like X but closer/quieter"
- rank_spots_this_week(region="Queensland", skill="beginner")  # use this to COMPARE many spots in a state; optional filters: break_type, peak_type, max_crowd (quiet/moderate/busy/very crowded), avoid_hazards (e.g. "sharks"), limit (max 25)

OUTPUT CONTRACT (every answer with a pick):
1. One-line verdict first ("Best: X @ <day time> — <score>/10.").
2. Then 1-3 scored picks, each with its score_week (or find_best_windows) numbers cited as day/time + score + wave + wind.
3. Then one sentence WHY (cite explain_score_breakdown components: swell size/direction, wind, period).
4. Hazards/skill note when the knowledge profile has hazards or expert/pro-only tier (safety footer, one line).
5. Last line: name whose swell + wind graphs are shown below (matches rule 8 — every pick charted).

FEW-SHOT TRACES (follow these shapes):
A) "when should I surf Bells this week?"
   get_spot_knowledge(spot_name="Bells Beach", region="Victoria")
   → score_week(spot_name="Bells Beach", region="Victoria", skill="intermediate")
   → answer verdict + best window + why + graphs line.
B) "where should I surf in NSW as a beginner?"
   rank_spots_this_week(region="New South Wales", skill="beginner")
   → get_spot_knowledge + score_week for the top pick only
   → verdict + runner-up from the rank table (no extra scoring) + graphs line.
C) "Bells or Winkipop on Saturday morning?"
   score_week spot A + score_week spot B (max 3 score calls per question)
   → or find_best_windows(..., daypart="morning", weekend_only=True) per spot
   → pick the higher best + why + graphs line for both.

Workflow: to answer "where should I surf in <state>", call rank_spots_this_week first,
then get_spot_knowledge + score_week for the top 1-2 spots. Never invent keyword
names — use exactly the ones above. Call score_week (or at minimum
get_forecast) for EVERY spot you end up recommending, so each recommendation
gets its swell + wind graphs; mention in your answer that the graphs for each
recommended spot are displayed below.

TRACE / PAYLOAD NOTES:
- Tool payloads shown in the UI trace may be trimmed previews; your in-context
  tool outputs are complete. Never paste full payloads into your answer — summarize.
- `region` is optional when you genuinely don't know it: call
  find_spots(query="<spot name>") first and copy `region`/`state` from the
  results into later calls.

AMBIGUITY RULE:
- If get_spot_knowledge / get_forecast / score_week reports the spot was not
  found (or returns empty), do NOT guess another spot. Call
  find_spots(query="<name>") and ask the user to pick from the matches.

DATES:
- Resolve relative dates ("today", "tomorrow", "this weekend") against the
  timestamps in tool output. The forecast/score window covers ~7 days from now —
  never invent times outside it, and cite day/time labels exactly as returned.

STANCE (peak direction preference — advice only, never scores):
- Goofy-footers normally prefer lefts, natural-footers normally prefer rights.
- A-frames (and "both (separate peaks)") are neutral — good for either stance.
- Use the break's `peakType` from get_spot_knowledge to tailor the pick:
  steer goofy surfers toward lefts, natural surfers toward rights, and call
  out A-frames as stance-neutral options. Stance never changes numbers.

BUDGET:
- Call score_week at most THREE times per question (top 1-2 spots + one
  compare pick). Prefer find_best_windows over raw score_week for
  morning/weekend questions (one call answers the filter).
- For "where should I surf / best spot in <state>" questions, prefer
  rank_spots_this_week first, then drill into the top pick.

SAFETY:
- One-line caution when the knowledge profile lists hazards (sharks,
  sharp reef, rocks, rip currents) or skill is expert/pro-only. Never
  downplay hazards; never recommend a pro-only spot to a beginner —
  redirect to a similar beginner spot via find_similar_spots.
"""

HF_DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
PROVIDER = "deepinfra"
# Single-model lock per spec: tuned for concise surf answers.
MODEL_TEMPERATURE = 0.2
MODEL_MAX_TOKENS = 1500
MODEL_TIMEOUT = 120
AGENT_MAX_STEPS = 10

#: Max serialized length before a trace observation is stored as a truncated
#: preview string. Structured payloads needed downstream (e.g. score_week
#: hour lists consumed by main.py chart builders) are always kept whole under
#: ``observation``; the trimmed form lives in ``observation_preview``.
MAX_OBSERVATION_CHARS = 4000


def _truncate_text(text: str, limit: int = MAX_OBSERVATION_CHARS) -> tuple[str, bool]:
    """Truncate *text* to *limit* chars. Returns (text, was_truncated)."""
    if len(text) <= limit:
        return text, False
    return text[:limit] + f"... [truncated {len(text) - limit} chars]", True


def _observation_preview(observation: Any) -> tuple[str, bool]:
    """Serialize *observation* to a display string of at most ~4000 chars."""
    if isinstance(observation, str):
        return _truncate_text(observation)
    try:
        text = json.dumps(observation, default=str)
    except (TypeError, ValueError):
        text = str(observation)
    return _truncate_text(text)


def _summarize_observation(observation: Any) -> str:
    """One-line summary of a tool observation for ("tool_end", ...) events."""
    if isinstance(observation, dict):
        # score_week wrapper: surface spot + hours, not raw keys.
        if isinstance(observation.get("scored"), list):
            spot = observation.get("spot") or {}
            label = spot.get("name") or "spot"
            skill = observation.get("skill")
            suffix = f" for {skill}" if skill else ""
            return f"{len(observation['scored'])} scored hour(s) for {label}{suffix}"
        if isinstance(observation.get("windows"), list):
            spot = observation.get("spot") or {}
            label = spot.get("name") or "spot"
            return f"{len(observation['windows'])} window(s) for {label}"
        if "error" in observation:
            return f"error: {observation.get('error')}"
        if isinstance(observation.get("rank"), list):
            return f"list[{len(observation['rank'])}]"
        keys = ",".join(list(observation.keys())[:6])
        return f"dict[{keys}]"
    if isinstance(observation, list):
        if observation and isinstance(observation[0], dict) and "best_score" in observation[0]:
            top = observation[0]
            return (
                f"{len(observation)} spot(s) ranked "
                f"(top: {top.get('name', '?')} {top.get('best_score', '?')}/10)"
            )
        return f"list[{len(observation)}]"
    text = observation if isinstance(observation, str) else str(observation)
    return text[:200] if len(text) > 200 else text


def get_default_model() -> str:
    """Return the single supported model."""
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

    def add_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append(
            TraceEvent(type=event_type, timestamp=time.time(), data=data)
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "question": self.question,
                "model": self.model,
                "events": [
                    {"type": e.type, "timestamp": e.timestamp, "data": e.data}
                    for e in self.events
                ],
            },
            default=str,
        )


class GetForecastTool(Tool):
    name = "get_forecast"
    description = "Get hourly marine + wind forecast for a named spot."
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot (e.g., 'Snapper Rocks')"},
        "region": {"type": "string", "description": "State name or sub-region (e.g. 'Queensland', 'Central Coast'; codes NSW, QLD, VIC, WA, SA, TAS accepted)"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_forecast(spot_name, region)


class ScoreWeekTool(Tool):
    name = "score_week"
    description = (
        "Get hour-by-hour surf scores for the next 7 days at ONE spot. "
        "Example: score_week(spot_name=\"Snapper Rocks\", region=\"Queensland\", skill=\"intermediate\"). "
        "To compare many spots, use rank_spots_this_week instead."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "State name or sub-region"},
        "skill": {"type": "string", "description": "Surfer skill level (beginner, intermediate, advanced, expert, pro-only)", "nullable": True},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str, skill: str | None = None) -> list[dict]:
        return score_week(spot_name, region, skill=skill)


class FindSpotsTool(Tool):
    name = "find_spots"
    description = (
        "Search breaks by name or state with optional skill filter. "
        "Example: find_spots(query=\"Queensland\", skill=\"beginner\")"
    )
    inputs = {
        "query": {"type": "string", "description": "Spot name OR state name/code (e.g. Queensland/QLD, New South Wales/NSW, Victoria/VIC, Western Australia/WA, South Australia/SA, Tasmania/TAS)", "nullable": True},
        "region": {"type": "string", "description": "Alias for query when searching a state name or sub-region", "nullable": True},
        "skill": {"type": "string", "description": "Skill level filter (beginner, intermediate, advanced, expert, pro-only)", "nullable": True},
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
        "region": {"type": "string", "description": "State name or sub-region"},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str) -> dict:
        return get_spot_knowledge(spot_name, region)


class RankSpotsThisWeekTool(Tool):
    name = "rank_spots_this_week"
    description = (
        "Rank ALL spots in a state by their best score this week. "
        "Example: rank_spots_this_week(region=\"Queensland\", skill=\"beginner\"). "
        "Optional filters: break_type, peak_type, max_crowd "
        "(quiet/moderate/busy/very crowded), avoid_hazards (e.g. 'sharks'), limit (max 25). "
        "Use this first for 'where should I surf' questions."
    )
    inputs = {
        "region": {"type": "string", "description": "State name or sub-region"},
        "skill": {"type": "string", "description": "Skill level filter", "nullable": True},
        "break_type": {"type": "string", "description": "Break type filter (reef, beach, point, river mouth, slab, jetty/groin, man-made/artificial)", "nullable": True},
        "peak_type": {"type": "string", "description": "Peak type filter (left, right, a-frame, both (separate peaks), closeout)", "nullable": True},
        "max_crowd": {"type": "string", "description": "Crowd cap (quiet, moderate, busy, very crowded)", "nullable": True},
        "avoid_hazards": {"type": "string", "description": "Hazard to exclude (e.g. sharks, rocks, rip currents)", "nullable": True},
        "limit": {"type": "integer", "description": "Max spots to rank (1-25)", "nullable": True},
    }
    output_type = "object"

    def forward(
        self,
        region: str,
        skill: str | None = None,
        break_type: str | None = None,
        peak_type: str | None = None,
        max_crowd: str | None = None,
        avoid_hazards: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        return rank_spots_this_week(
            region,
            skill,
            break_type=break_type,
            peak_type=peak_type,
            max_crowd=max_crowd,
            avoid_hazards=avoid_hazards,
            limit=limit or 15,
        )


class ExplainScoreBreakdownTool(Tool):
    name = "explain_score_breakdown"
    description = (
        "Explain WHY one scored hour got its score: component split "
        "(swell size/direction, wind, period) plus raw inputs. "
        "Call before explaining what drove a score."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "State name or sub-region", "nullable": True},
        "skill": {"type": "string", "description": "Surfer skill level", "nullable": True},
        "time": {"type": "string", "description": "Hour substring to explain (default: best hour)", "nullable": True},
    }
    output_type = "object"

    def forward(
        self,
        spot_name: str,
        region: str | None = None,
        skill: str | None = None,
        time: str | None = None,
    ) -> dict:
        return explain_score_breakdown(spot_name, region, skill=skill, time=time)


class FindBestWindowsTool(Tool):
    name = "find_best_windows"
    description = (
        "Best scored windows for ONE spot with daypart/weekend filters. "
        "daypart: morning/midday/afternoon/all. Use for 'mornings' or "
        "'weekend' questions instead of doing time math yourself."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "State name or sub-region", "nullable": True},
        "skill": {"type": "string", "description": "Surfer skill level", "nullable": True},
        "daypart": {"type": "string", "description": "morning, midday, afternoon, or all", "nullable": True},
        "weekend_only": {"type": "boolean", "description": "Only Saturday/Sunday", "nullable": True},
        "min_score": {"type": "number", "description": "Minimum score threshold", "nullable": True},
        "limit": {"type": "integer", "description": "Max windows to return (1-10)", "nullable": True},
    }
    output_type = "object"

    def forward(
        self,
        spot_name: str,
        region: str | None = None,
        skill: str | None = None,
        daypart: str | None = None,
        weekend_only: bool = False,
        min_score: float | None = None,
        limit: int | None = None,
    ) -> dict:
        return find_best_windows(
            spot_name,
            region,
            skill=skill,
            daypart=daypart,
            weekend_only=bool(weekend_only),
            min_score=min_score or 0.0,
            limit=limit or 5,
        )


class FindSimilarSpotsTool(Tool):
    name = "find_similar_spots"
    description = (
        "Find breaks similar to a reference break (same skill/type/peak/swell). "
        "Use for 'like X but quieter/closer/easier' questions."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Reference spot name"},
        "region": {"type": "string", "description": "State name or sub-region", "nullable": True},
        "skill": {"type": "string", "description": "Skill level filter", "nullable": True},
        "limit": {"type": "integer", "description": "Max results (1-10)", "nullable": True},
    }
    output_type = "object"

    def forward(
        self,
        spot_name: str,
        region: str | None = None,
        skill: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        return find_similar_spots(spot_name, region, skill=skill, limit=limit or 5)


class ListStatesRegionsTool(Tool):
    name = "list_states_regions"
    description = (
        "List canonical states + regions vocabulary. Call when unsure of a "
        "region spelling instead of guessing."
    )
    inputs = {}
    output_type = "object"

    def forward(self) -> dict:
        return list_states_regions()


class GetSpotSunSstTool(Tool):
    name = "get_spot_sun_sst"
    description = (
        "Sunrise/sunset + sea-surface temp + wetsuit hint for a spot "
        "(from the cached Open-Meteo frame, no new API)."
    )
    inputs = {
        "spot_name": {"type": "string", "description": "Name of the surf spot"},
        "region": {"type": "string", "description": "State name or sub-region", "nullable": True},
    }
    output_type = "object"

    def forward(self, spot_name: str, region: str | None = None) -> dict:
        return get_spot_sun_sst(spot_name, region)


TOOLS = [
    GetForecastTool(),
    ScoreWeekTool(),
    FindSpotsTool(),
    GetSpotKnowledgeTool(),
    RankSpotsThisWeekTool(),
    ExplainScoreBreakdownTool(),
    FindBestWindowsTool(),
    FindSimilarSpotsTool(),
    ListStatesRegionsTool(),
    GetSpotSunSstTool(),
]


def _build_model(
    model: str | None = None,
    hf_token: str | None = None,
) -> InferenceClientModel:
    """Build the HF Inference Providers model client (provider=deepinfra).

    Token priority: explicit hf_token arg > HF_TOKEN env var.
    """
    model_id = model or HF_DEFAULT_MODEL
    token = (hf_token or "").strip() or os.getenv("HF_TOKEN") or ""
    if not token:
        raise ValueError(
            "HF_TOKEN not set — enter your Hugging Face token in the UI or set HF_TOKEN in your environment "
            "(https://huggingface.co/settings/tokens). The token is used for HF Inference Providers (deepinfra)."
        )
    return InferenceClientModel(
        model_id=model_id,
        provider=PROVIDER,
        token=token,
        temperature=MODEL_TEMPERATURE,
        max_tokens=MODEL_MAX_TOKENS,
        timeout=MODEL_TIMEOUT,
    )


def _load_prompt_templates() -> PromptTemplates:
    default_templates_yaml = (
        importlib.resources.files("smolagents.prompts")
        .joinpath("code_agent.yaml")
        .read_text()
    )
    default_templates = yaml.safe_load(default_templates_yaml)
    default_templates["system_prompt"] += "\n\n" + SYSTEM_PROMPT
    return PromptTemplates(**default_templates)


class SurfAgent:
    """Surf forecasting agent with streaming and trace capture."""

    def __init__(
        self,
        hf_token: str | None = None,
        model: str | None = None,
        max_steps: int = AGENT_MAX_STEPS,
    ):
        self.model = model or HF_DEFAULT_MODEL
        self._model = _build_model(self.model, hf_token=hf_token)
        self._trace: AgentTrace | None = None
        self._tool_start_times: dict[Any, float] = {}
        # Inner CodeAgent tool events queued by the per-tool wrappers
        # below; flushed as ("tool_start", ...)/("tool_end", ...) in run_stream.
        self._pending_stream: list[tuple[str, dict[str, Any]]] = []
        self._agent = CodeAgent(
            tools=self._make_traced_tools(),
            model=self._model,
            prompt_templates=_load_prompt_templates(),
            max_steps=max_steps,
        )
        self._trace: AgentTrace | None = None
        self._tool_start_times: dict[Any, float] = {}

    def _make_traced_tools(self) -> list[Tool]:
        """Fresh per-agent tool instances wrapped to record trace events.

        CodeAgent executes tools *inside* the python_interpreter code step,
        so smolagents never yields SmolToolCall/ToolOutput for score_week
        etc. — only ``ToolCall(name="python_interpreter")``. Wrapping each
        tool's ``forward`` here records proper ``tool_call``/``tool_result``
        events with the full observation (charts need it) plus queued
        stream events for progressive UI updates. Fresh instances per agent
        avoid stacking wrappers across sessions (TOOLS prototypes stay clean).
        """
        traced: list[Tool] = []
        for proto in TOOLS:
            inst = type(proto)()
            orig_forward = inst.forward
            tool_name = inst.name
            inst.forward = self._wrap_forward(orig_forward, tool_name)  # type: ignore[method-assign]
            traced.append(inst)
        return traced

    def _wrap_forward(self, orig_forward, tool_name: str):
        """Wrap a tool forward() to trace calls + queue stream events."""
        agent_ref = self

        def wrapper(*args, **kwargs):
            try:
                sig = inspect.signature(orig_forward)
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                arguments = dict(bound.arguments)
            except (TypeError, ValueError):
                if kwargs:
                    arguments = dict(kwargs)
                elif args:
                    arguments = {"args": list(args)}
                else:
                    arguments = {}
            call_id = f"{tool_name}_{time.time_ns()}"
            start = time.time()
            if agent_ref._trace is not None:
                agent_ref._trace.add_event(
                    "tool_call",
                    {"name": tool_name, "arguments": arguments, "id": call_id},
                )
            agent_ref._pending_stream.append(
                ("tool_start", {"name": tool_name, "arguments": arguments})
            )
            try:
                result = orig_forward(*args, **kwargs)
            except Exception as exc:  # surface failures, keep streaming
                err_obs: dict[str, Any] = {"error": str(exc)}
                duration_ms = round((time.time() - start) * 1000, 1)
                if agent_ref._trace is not None:
                    agent_ref._trace.add_event(
                        "tool_result",
                        {
                            "name": tool_name,
                            "arguments": arguments,
                            "observation": err_obs,
                            "observation_preview": str(err_obs)[:4000],
                            "truncated": False,
                            "duration_ms": duration_ms,
                            "id": call_id,
                        },
                    )
                agent_ref._pending_stream.append(
                    (
                        "tool_end",
                        {
                            "name": tool_name,
                            "ms": duration_ms,
                            "summary": f"error: {exc}",
                            "observation": err_obs,
                            "arguments": arguments,
                        },
                    )
                )
                raise
            duration_ms = round((time.time() - start) * 1000, 1)
            if agent_ref._trace is not None:
                preview, truncated = _observation_preview(result)
                agent_ref._trace.add_event(
                    "tool_result",
                    {
                        "name": tool_name,
                        "arguments": arguments,
                        "observation": result,
                        "observation_preview": preview,
                        "truncated": truncated,
                        "duration_ms": duration_ms,
                        "id": call_id,
                    },
                )
            agent_ref._pending_stream.append(
                (
                    "tool_end",
                    {
                        "name": tool_name,
                        "ms": duration_ms,
                        "summary": _summarize_observation(result),
                        "observation": result,
                        "arguments": arguments,
                    },
                )
            )
            return result

        return wrapper

    def _flush_pending_stream(self) -> Generator[tuple[str, Any], None, None]:
        """Yield queued inner-tool start/end events (FIFO)."""
        while self._pending_stream:
            kind, data = self._pending_stream.pop(0)
            yield (kind, data)

    @property
    def trace(self) -> AgentTrace | None:
        return self._trace

    def _capture_item(self, item: Any) -> bool:
        """Record a tool_call/tool_result from a smolagents stream item.

        On SmolToolCall the wall-clock start time is stored (keyed by call
        id); on ToolOutput the elapsed time becomes ``duration_ms``. The raw
        observation (dict/list/str) is kept whole under ``observation`` so
        downstream chart builders keep working; a ~4000-char trimmed form is
        stored alongside as ``observation_preview`` with a ``truncated`` flag.

        CodeAgent-only note: ``python_interpreter`` pseudo-calls are skipped —
        inner surf tools are traced by the per-tool wrappers instead (see
        ``_make_traced_tools``), otherwise the UI shows N×
        ``[tool: python_interpreter] args={}`` with no chartable payload.
        """
        if self._trace is None:
            return False
        if isinstance(item, SmolToolCall):
            if item.name == "python_interpreter":
                return False
            self._tool_start_times[item.id] = time.time()
            self._trace.add_event(
                "tool_call",
                {"name": item.name, "arguments": item.arguments, "id": item.id},
            )
            return True
        if isinstance(item, ToolOutput):
            tool_call = item.tool_call
            name = tool_call.name if tool_call is not None else None
            arguments = getattr(tool_call, "arguments", None)
            call_id = getattr(tool_call, "id", None)
            start = self._tool_start_times.pop(call_id, None)
            duration_ms = (
                round((time.time() - start) * 1000, 1) if start is not None else None
            )
            observation = item.observation
            preview, truncated = _observation_preview(observation)
            self._trace.add_event(
                "tool_result",
                {
                    "name": name,
                    "arguments": arguments,
                    "observation": observation,
                    "observation_preview": preview,
                    "truncated": truncated,
                    "duration_ms": duration_ms,
                },
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
        self._trace = AgentTrace(question=question, model=self.model)
        self._tool_start_times = {}
        self._pending_stream = []
        try:
            original_step_stream = self._agent._step_stream
        except AttributeError:
            original_step_stream = None
        if original_step_stream is None:
            return self._agent.run(question)
        self._agent._step_stream = self._traced_step_stream(original_step_stream)
        try:
            return self._agent.run(question)
        finally:
            self._agent._step_stream = original_step_stream

    def run_stream(
        self, question: str
    ) -> Generator[tuple[str, Any], None, None]:
        """Run the agent with streaming.

        Yields ("model", delta) for LLM tokens and ("final", answer) at the
        end. For tool calls it yields BOTH the legacy compat event
        ("tool", tool_name) and richer detail events:
        ("tool_start", {"name", "arguments"}) when the call fires and
        ("tool_end", {"name", "ms", "summary", "observation", "arguments"})
        when its output arrives. Code the agent executes is surfaced as
        ("code", code_text) so the UI can show parsed tool lines while the
        output loads. Existing consumers that only handle ("model", ...),
        ("tool", ...) and ("final", ...) keep working unchanged — unknown
        event kinds can be safely ignored.

        CodeAgent note: smolagents yields ``ToolCall(name="python_interpreter")``
        for every code step — those are swallowed here (noisy, args={},
        no chartable payload). Real surf-tool activity comes from the
        per-tool wrappers (``_make_traced_tools``) and is flushed on each
        ActionOutput/ActionStep.
        """
        self._trace = AgentTrace(question=question, model=self.model)
        self._tool_start_times = {}
        self._pending_stream = []
        for item in self._agent.run(question, stream=True):
            if isinstance(item, ChatMessageStreamDelta):
                if item.content:
                    self._trace.add_event("llm_chunk", {"chunk": item.content})
                    yield ("model", item.content)
                continue
            if isinstance(item, FinalAnswerStep):
                # Flush any trailing inner-tool events first so charts can
                # render before the final bubble lands.
                yield from self._flush_pending_stream()
                self._trace.add_event("final_answer", {"answer": item.output})
                yield ("final", item.output)
                continue
            if isinstance(item, SmolToolCall):
                if item.name == "python_interpreter":
                    # Swallow CodeAgent code-exec pseudo-calls; the real
                    # surf-tool calls arrive via _pending_stream.
                    continue
                self._capture_item(item)
                name = item.name if isinstance(item.name, str) else "code action"
                yield ("tool", name)  # backward-compat alias for tool_start
                yield ("tool_start", {"name": name, "arguments": item.arguments})
                continue
            if isinstance(item, ToolOutput):
                captured = self._capture_item(item)
                if captured:
                    data = self._trace.events[-1].data if self._trace.events else {}
                    yield (
                        "tool_end",
                        {
                            "name": data.get("name"),
                            "ms": data.get("duration_ms"),
                            "summary": _summarize_observation(data.get("observation")),
                            "observation": data.get("observation"),
                            "arguments": data.get("arguments"),
                        },
                    )
                # Flush any inner-tool events queued during code execution.
                yield from self._flush_pending_stream()
                continue
            if isinstance(item, ActionOutput):
                # Code finished executing — inner tools (if any) ran during
                # the step; flush them as proper tool_start/tool_end pairs
                # BEFORE the code event so progressive charts update promptly.
                for kind, data in self._flush_pending_stream():
                    if kind == "tool_start":
                        yield ("tool", str(data.get("name", "?")))
                    yield (kind, data)
                continue
            if isinstance(item, ActionStep):
                for kind, data in self._flush_pending_stream():
                    if kind == "tool_start":
                        yield ("tool", str(data.get("name", "?")))
                    yield (kind, data)
                code_action = getattr(item, "code_action", None)
                if isinstance(code_action, str) and code_action.strip():
                    self._trace.add_event("code_action", {"code": code_action})
                    yield ("code", code_action)
                continue
            self._capture_item(item)
        # Safety net: flush anything left (e.g. max-steps path with no final).
        yield from self._flush_pending_stream()


def run_agent(
    question: str,
    hf_token: str | None = None,
    model: str | None = None,
    max_steps: int = AGENT_MAX_STEPS,
) -> str:
    """Run the surf agent and return the answer."""
    agent = SurfAgent(hf_token=hf_token, model=model, max_steps=max_steps)
    return agent.run(question)


def run_agent_stream(
    question: str,
    hf_token: str | None = None,
    model: str | None = None,
    max_steps: int = AGENT_MAX_STEPS,
):
    """Run the surf agent with streaming."""
    agent = SurfAgent(hf_token=hf_token, model=model, max_steps=max_steps)
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
        elif kind == "tool_start":
            print(f"\n[tool_start: {chunk.get('name')} args={chunk.get('arguments')}]", flush=True)
        elif kind == "tool_end":
            print(f"\n[tool_end: {chunk.get('name')} {chunk.get('ms')}ms {chunk.get('summary')}]", flush=True)
    print()
