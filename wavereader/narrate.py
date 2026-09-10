"""Streamed surf-report narration (Worker C).

Port of ``app/generate_surf_report.py`` onto the :mod:`wavereader.llm`
factory: daily scored summaries IN, streamed markdown OUT. The LLM never
owns numbers — it narrates only the provided deterministic scores.

Keeps the ``<think>``/``@@REPORT@@`` marker-stripping streaming pattern from
the original. Single-model rule: Nemotron 3 Ultra 550B via
deepinfra (``WR_*`` env overrides); no Qwen references.
"""

from __future__ import annotations

import re
from typing import Any, Generator, Optional

from wavereader import llm as _llm

MAX_TOKENS = 800
TEMPERATURE = 0.3

# Reasoning stays out of the visible text: the model is told not to think
# out loud, and the cleaning layer below is the safety net.
SYSTEM_PROMPT = "/no_think\nWrite only the final surf summary. Never reveal thinking, reasoning, or planning."
EXTRA_BODY = {"reasoning_effort": "none"}


def _day_line(d: dict) -> str:
    """One daily best as a single compact line for the prompt."""
    d = d or {}
    date = d.get("date") or str(d.get("time") or "")[:10] or "?"
    return (
        f"{date} {d.get('time')} | score={d.get('score')}/10 | "
        f"wave={d.get('wave_height_m')}m@{d.get('wave_period_s')}s | "
        f"wind={d.get('wind_speed_kt')}kt@{d.get('wind_direction_deg')}deg"
    )


def _break_line(break_: dict) -> str:
    """One-line break context: ideals + hazards only, truncated."""
    swell = (break_ or {}).get("idealSwell") or {}
    wind = (break_ or {}).get("idealWind") or {}
    size = swell.get("sizeRangeFt") or {}
    hazards = (break_ or {}).get("hazards") or []
    if isinstance(hazards, list):
        hazards = ", ".join(str(h) for h in hazards[:3])
    return (
        f"{break_.get('name')}, {break_.get('region')}, {break_.get('state')} | "
        f"ideal swell {swell.get('direction')} {size.get('min')}-{size.get('max')}ft | "
        f"ideal wind {wind.get('direction')} | hazards: {hazards}"
    )


def build_report_prompt(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: Optional[dict],
    days: int,
) -> str:
    """Assemble the tiny report prompt: daily bests + best window only."""
    daily_block = "\n".join(_day_line(d) for d in (daily or []))
    best_block = _day_line(best) if best else "none"
    return f"""You are a surf report writer. You narrate deterministic forecast scores -- you never invent numbers.

Rules:
1. Wrap your ENTIRE response between these markers, on their own lines, with NOTHING outside them -- no intro, no thinking, no notes, no commentary:
@@REPORT@@
<your dot-point report, then recommendation line>
@@END@@
2. NEVER show your thinking, reasoning, planning, or notes to yourself. Do NOT use <think> tags or any reasoning preamble -- the first thing you emit is @@REPORT@@, the last thing is @@END@@.
3. Use ONLY the numbers/times below. Never invent wave heights, periods, wind speeds, directions, or scores.
4. Write one dot-point (markdown bullet starting with "- ") per day below, in date order, for a {skill} surfer. Each bullet names the date with its score, wave height/period and wind, followed by one full sentence explaining the outlook in plain language. If a day scores poorly, say so plainly. One bullet per day, no extra bullets.
5. After the bullets, add a blank line then exactly one line: **Recommendation: <date + time> -- <one short reason>.** naming the single best day/window to surf.

Break: {_break_line(break_ or {})}
Skill: {skill} | Window: {days} day(s)

Best window: {best_block}

Daily bests:
{daily_block}

Report:"""


def _strip_fences(text: str) -> str:
    """Remove stray code fences if the model added them anyway."""
    text = (text or "").strip()
    fence_match = re.search(r"```(?:\w+)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()
    return text


_THINK_RE = re.compile(
    r"<\s*(think|thinking|reason|reasoning)[^>]*>.*?(<\s*/\s*\1\s*>|$)",
    re.DOTALL | re.IGNORECASE,
)
_STRAY_TAG_RE = re.compile(r"<\s*/?\s*(think|thinking|reason|reasoning)[^>]*>", re.IGNORECASE)

_REPORT_START = "@@REPORT@@"
_REPORT_END = "@@END@@"

_META_PHRASES = (
    "we need to",
    "i need to",
    "need to produce",
    "need to output",
    "must end with",
    "must include",
    "must name",
    "the best window given",
    "requirement",
    "need to ",
    "plan:",
    "thinking:",
    "reasoning:",
)

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _drop_thinking_sentences(text: str) -> str:
    """Remove plain-text planning sentences; "" if nothing remains."""
    parts = [p for p in _SENT_SPLIT_RE.split(text or "") if p.strip()]
    kept = [p for p in parts if not any(m in p.lower() for m in _META_PHRASES)]
    if any(p.lstrip().startswith(("-", "*")) for p in kept):
        return "\n".join(kept).strip()
    return " ".join(kept).strip()


def _clean_output(text: str) -> str:
    """Strip reasoning traces + markers + fences so only the summary remains."""
    text = text or ""
    text = _THINK_RE.sub("", text)
    text = _STRAY_TAG_RE.sub("", text)
    if _REPORT_START in text:
        after = text.split(_REPORT_START, 1)[1]
        if _REPORT_END in after:
            after = after.split(_REPORT_END, 1)[0]
        return _strip_fences(after).strip()
    cleaned = _strip_fences(text).strip()
    if not cleaned:
        return ""
    return _drop_thinking_sentences(cleaned)


def _messages(break_: dict, skill: str, daily: list[dict], best: Optional[dict], days: int) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_report_prompt(break_, skill, daily, best, days)},
    ]


def generate_report(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: Optional[dict],
    days: int,
    hf_token: Optional[str] = None,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
) -> str:
    """Generate the short plain-markdown report in one LLM call."""
    client = _llm.get_client(hf_token)
    completion = client.chat.completions.create(
        model=_llm.get_model_id(),
        messages=_messages(break_, skill, daily, best, days),
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=EXTRA_BODY,
    )
    return _clean_output(completion.choices[0].message.content)


def generate_report_stream(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: Optional[dict],
    days: int,
    hf_token: Optional[str] = None,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
    stats: Optional[dict] = None,
) -> Generator[str, None, None]:
    """Stream the report: yields accumulated cleaned markdown per delta."""
    client = _llm.get_client(hf_token)
    stream = client.chat.completions.create(
        model=_llm.get_model_id(),
        messages=_messages(break_, skill, daily, best, days),
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
        extra_body=EXTRA_BODY,
    )
    accumulated = ""
    reasoning_chars = 0
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta
        except (AttributeError, IndexError):
            delta = None
        content = getattr(delta, "content", None) if delta is not None else None
        reasoning = getattr(delta, "reasoning_content", None) if delta is not None else None
        if reasoning:
            reasoning_chars += len(reasoning)
        if content:
            accumulated += content
            yield _clean_output(accumulated)
    if stats is not None:
        stats["reasoning_chars"] = reasoning_chars
        stats["content_chars"] = len(accumulated)
        stats["model"] = _llm.get_model_id()
        stats["provider"] = _llm.get_provider()
    if accumulated:
        yield _clean_output(accumulated)


def narrate_day(daily_row: dict) -> str:
    """Deterministic one-line narration of a daily best (no LLM)."""
    d = daily_row or {}
    date = d.get("date") or str(d.get("time") or "")[:10]
    return (
        f"{date}: {d.get('score')}/10, "
        f"{d.get('wave_height_m')}m @ {d.get('wave_period_s')}s, "
        f"wind {d.get('wind_speed_kt')}kt. "
        f"Best at {d.get('time')}."
    )


__all__ = [
    "build_report_prompt",
    "generate_report",
    "generate_report_stream",
    "narrate_day",
    "_clean_output",
    "SYSTEM_PROMPT",
    "EXTRA_BODY",
    "MAX_TOKENS",
    "TEMPERATURE",
]
