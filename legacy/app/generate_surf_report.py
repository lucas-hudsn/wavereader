"""
Hugging Face Inference Providers + NVIDIA Nemotron 3 -- short surf report.

Same framework as ``generate_surf_break.py`` (deliberately NOT a smolagents
CodeAgent -- single-shot call via ``InferenceClient.chat.completions.create``).

Speed-first design (TTFT is dominated by prompt prefill + output length):

- The prompt carries ONLY the daily bests (<=7 lines) + the single best
  window + a one-line break summary. The old version sent every scored
  hour (~168 rows for 7 days) plus the full break record -- that prefill
  is what made generation feel like it never started.
- Output is plain markdown, NOT JSON: one dot-point (bullet) per day
  covering the day-by-day outlook (one full sentence per day), plus a final
  line naming the single best day/window to surf. Short output
  (~350 tokens) with ``max_tokens=800``.
- Plain text also streams cleanly: what the user watches arrive IS the
  report -- no JSON escape decoding or partial-parse step.

The LLM never owns numbers -- scores/forecasts stay deterministic in
``app/scoring.py`` + ``app/forecasts.py``. The prompt instructs the model to
narrate only the provided numbers, never invent swell/wind/score values.

Requires ``HF_TOKEN`` env (Inference Providers access).
"""

from __future__ import annotations

import os
import re
import sys

from huggingface_hub import InferenceClient

MODEL_ID = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
PROVIDER = "deepinfra"

MAX_TOKENS = 800
TEMPERATURE = 0.3

# Reasoning runs in a separate channel, not in the visible text:
# - DeepInfra honors ``reasoning_effort: "none"`` (disables chain-of-thought
#   entirely: faster, cheaper, direct answer). Passed via ``extra_body``.
# - Nemotron itself honors the ``/no_think`` system-prompt directive.
# Without these, the model can spend the whole token budget "thinking" and
# leave nothing for the report -- which is exactly the blank output seen
# in the UI. Marker/cleaning logic below stays as a safety net.
SYSTEM_PROMPT = "/no_think\nWrite only the final surf summary. Never reveal thinking, reasoning, or planning."
EXTRA_BODY = {"reasoning_effort": "none"}


def _day_line(d: dict) -> str:
    """One daily best as a single compact line for the prompt."""
    d = d or {}
    # best_window() returns a raw scored row with no 'date' key -- derive
    # it from the timestamp so the model never sees a "None" date (which
    # visibly confused it into reasoning out loud about what "None" means).
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


def build_surf_report_prompt(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: dict | None,
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
4. Write one dot-point (markdown bullet starting with "- ") per day below, in date order, for a {skill} surfer. Each bullet names the date with its score, wave height/period and wind, followed by one full sentence explaining the outlook in plain language (e.g. what the conditions will feel like and whether it suits a {skill} surfer). If a day scores poorly, say so plainly in a full sentence. One bullet per day, no extra bullets.
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
_STRAY_TAG_RE = re.compile(
    r"<\s*/?\s*(think|thinking|reason|reasoning)[^>]*>", re.IGNORECASE
)


_REPORT_START = "@@REPORT@@"
_REPORT_END = "@@END@@"

# Sentences containing these phrases (case-insensitive) are model
# planning/thinking leaked as plain text (no <think> tags), e.g. "We need
# to produce dot-points...". Kept narrow on purpose: ordinary surf outlook
# words ("could be", "probably", "should be") are legit report language
# and must never be filtered.
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
    """Remove plain-text planning sentences; return "" if nothing remains.

    Joins with newlines when the text is a dot-point list so bullets
    survive the fallback path; otherwise joins with spaces.
    """
    parts = [p for p in _SENT_SPLIT_RE.split(text or "") if p.strip()]
    kept = [
        p for p in parts if not any(m in p.lower() for m in _META_PHRASES)
    ]
    if any(p.lstrip().startswith(("-", "*")) for p in kept):
        return "\n".join(kept).strip()
    return " ".join(kept).strip()


def _clean_output(text: str) -> str:
    """Strip reasoning traces + markers + fences so only the summary remains.

    Three layers, in order:

    1. ``<think>...</think>`` blocks (complete or unclosed mid-stream).
    2. ``@@REPORT@@ ... @@END@@`` markers: everything outside them is
       discarded. Mid-stream (start seen, end not yet) returns whatever
       follows the start marker; pre-marker thinking yields "" so the UI
       shows its streaming placeholder instead of the model's planning.
    3. Fallback when the model ignores the markers: drop plain-text
       planning sentences ("We need to produce...", "Probably best
       is..."). Returns "" when only thinking has arrived so far.
    """
    text = text or ""
    # Remove complete <think>...</think> blocks, and a trailing unclosed
    # <think>... block (common mid-stream).
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
    filtered = _drop_thinking_sentences(cleaned)
    return filtered


def generate_surf_report(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: dict | None,
    days: int,
    model_id: str = MODEL_ID,
    provider: str = PROVIDER,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
) -> str:
    """Generate the short plain-markdown report in one LLM call."""
    client = InferenceClient(provider=provider, api_key=os.environ.get("HF_TOKEN"))

    prompt = build_surf_report_prompt(
        break_=break_, skill=skill, daily=daily, best=best, days=days
    )

    completion = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        extra_body=EXTRA_BODY,
    )

    return _clean_output(completion.choices[0].message.content)


def generate_surf_report_stream(
    break_: dict,
    skill: str,
    daily: list[dict],
    best: dict | None,
    days: int,
    model_id: str = MODEL_ID,
    provider: str = PROVIDER,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
    stats: dict | None = None,
):
    """Stream the short report token-by-token.

    Yields the accumulated plain-text report after every delta, so the
    Gradio handler displays exactly what the user will read -- no
    post-parse step needed. Reasoning is disabled at the API level
    (``reasoning_effort: "none"`` + ``/no_think``), so ``delta.content``
    carries the final answer; anything thinking-shaped that still slips
    through is stripped live. If ``stats`` is given, it is filled with
    ``reasoning_chars`` (hidden reasoning-channel text, never displayed)
    and ``content_chars`` so callers can prove the visible text is the
    final report, not the thinking stage.
    """
    client = InferenceClient(provider=provider, api_key=os.environ.get("HF_TOKEN"))

    prompt = build_surf_report_prompt(
        break_=break_, skill=skill, daily=daily, best=best, days=days
    )

    stream = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
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
        # Reasoning channel, when present, stays hidden -- counted only.
        reasoning = getattr(delta, "reasoning_content", None) if delta is not None else None
        if reasoning:
            reasoning_chars += len(reasoning)
        if content:
            accumulated += content
            yield _clean_output(accumulated)
    if stats is not None:
        stats["reasoning_chars"] = reasoning_chars
        stats["content_chars"] = len(accumulated)
    if accumulated:
        yield _clean_output(accumulated)


if __name__ == "__main__":
    print("Usage: import generate_surf_report() from main.py -- no standalone CLI.")
    sys.exit(0)
