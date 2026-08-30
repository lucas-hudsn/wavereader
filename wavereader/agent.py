"""Hand-rolled agent tool loop (~100 lines, no LangChain / no frameworks).

Provider-agnostic: one OpenAI-compatible client class; base URL + key come
from env (``HF_TOKEN`` -> https://router.huggingface.co/v1,
``NVIDIA_API_KEY`` -> https://integrate.api.nvidia.com/v1). Default model:
``Qwen/Qwen3-Next-80B-A3B-Instruct`` (only tested model supporting both
OpenAI-style tool calling and strict ``json_schema`` on the HF router — see
``data/GENERATION.md`` before swapping models).

The agent interprets and explains only; all numbers come from scoring.py /
forecasts.py via the tools in tools.py. Streaming + trace capture for the UI
trace panel.
"""

from __future__ import annotations


def run_agent(question: str, model: str | None = None) -> str:
    """Run the tool loop to answer a surf question.

    TODO: system prompt, tool dispatch loop (tools.py), streaming output,
    trace capture, provider switch via env.
    """
    raise NotImplementedError
