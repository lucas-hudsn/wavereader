"""
Seafloor explainer on the HF free tier (hf-inference).

Same framework as ``generate_surf_report.py`` (single-shot chat via
``InferenceClient.chat.completions.create``) but pointed at a small
open-weights chat model served on the ``hf-inference`` provider, which
fits inside the free monthly credit — no DeepInfra/Fireworks routing.

The LLM never owns numbers: the prompt carries only the deterministic
stats + markdown from ``app/seafloor.analyze_grid`` plus a one-line
break summary. The model narrates those numbers in plain language and
must never invent depths, slopes, or coordinates.
"""

from __future__ import annotations

import os
import re

from huggingface_hub import InferenceClient

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"
PROVIDER = "hf-inference"

MAX_TOKENS = 500
TEMPERATURE = 0.3

SYSTEM_PROMPT = "Write only the final seafloor summary. Never reveal thinking, reasoning, or planning."

_REPORT_START = "@@SEAFLOOR@@"
_REPORT_END = "@@END@@"

_THINK_RE = re.compile(
    r"<\s*(think|thinking|reason|reasoning)[^>]*>.*?(<\s*/\s*\1\s*>|$)",
    re.DOTALL | re.IGNORECASE,
)


def _stats_block(stats: dict) -> str:
    s = stats or {}
    return (
        f"dataset={s.get('dataset')} box={s.get('box_km')}km pts={s.get('points')} | "
        f"centre={s.get('center_elev_m')}m deepest={s.get('max_depth_m')}m "
        f"median_depth={s.get('median_depth_m')}m relief={s.get('relief_m')}m "
        f"land={s.get('land_fraction')} | shelf={s.get('shelf_class')} "
        f"median_slope={s.get('median_slope_m_per_km')}m/km "
        f"max_slope={s.get('max_slope_m_per_km')}m/km "
        f"channel_hint={s.get('channel_hint')}"
    )


def _break_line(break_: dict) -> str:
    b = break_ or {}
    swell = (b.get("idealSwell") or {})
    size = swell.get("sizeRangeFt") or {}
    return (
        f"{b.get('name')}, {b.get('region')}, {b.get('state')} | "
        f"type {b.get('breakType')}/{b.get('peakType')} lvl {b.get('skillLevel')} | "
        f"ideal swell {swell.get('direction')} {size.get('min')}-{size.get('max')}ft"
    )


def build_seafloor_prompt(break_: dict, stats: dict, analysis: str) -> str:
    """Assemble the tiny explainer prompt: stats + deterministic read only."""
    return f"""You are a surf seafloor explainer. You narrate deterministic bathymetry stats -- you never invent numbers.

Rules:
1. Wrap your ENTIRE response between these markers, on their own lines, with NOTHING outside them:
{_REPORT_START}
<your 4-6 sentence explanation>
{_REPORT_END}
2. Use ONLY the numbers/stats below. Never invent depths, slopes, coordinates, or channels.
3. Write 4-6 sentences in plain language for a surfer: what the shape is (shelf class), the depth range, what the slope means for how swell jacks up, and whether to expect punchier peaks or softer waves. Mention the channel hint only as given.
4. End with one short line: **Surf read:** <one sentence>.

Break: {_break_line(break_ or {})}
Stats: {_stats_block(stats or {})}

Deterministic read:
{analysis or '(none)'}

Explanation:"""


def _clean_output(text: str) -> str:
    text = text or ""
    text = _THINK_RE.sub("", text)
    if _REPORT_START in text:
        after = text.split(_REPORT_START, 1)[1]
        if _REPORT_END in after:
            after = after.split(_REPORT_END, 1)[0]
        return after.strip().strip("`").strip()
    return text.strip().strip("`").strip()


def generate_seafloor_explanation(
    break_: dict,
    stats: dict,
    analysis: str,
    model_id: str = MODEL_ID,
    provider: str = PROVIDER,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
) -> str:
    """One-shot seafloor explanation via the free-tier chat model."""
    client = InferenceClient(provider=provider, api_key=os.environ.get("HF_TOKEN"))
    prompt = build_seafloor_prompt(break_=break_, stats=stats, analysis=analysis)
    completion = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return _clean_output(completion.choices[0].message.content)


def generate_seafloor_explanation_stream(
    break_: dict,
    stats: dict,
    analysis: str,
    model_id: str = MODEL_ID,
    provider: str = PROVIDER,
    max_tokens: int = MAX_TOKENS,
    temperature: float = TEMPERATURE,
):
    """Stream the explanation token-by-token (yields cleaned text)."""
    client = InferenceClient(provider=provider, api_key=os.environ.get("HF_TOKEN"))
    prompt = build_seafloor_prompt(break_=break_, stats=stats, analysis=analysis)
    stream = client.chat.completions.create(
        model=model_id,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    accumulated = ""
    for chunk in stream:
        try:
            delta = chunk.choices[0].delta
        except (AttributeError, IndexError):
            delta = None
        content = getattr(delta, "content", None) if delta is not None else None
        if content:
            accumulated += content
            yield _clean_output(accumulated)
    if accumulated:
        yield _clean_output(accumulated)
