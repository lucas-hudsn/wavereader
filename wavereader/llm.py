"""One LLM client factory (Worker C — agent + narrator).

Single-model rule: every live LLM call in the v2 rebuild goes through
:func:`get_client` (raw ``InferenceClient``) or :func:`build_agent_model`
(smolagents ``InferenceClientModel``). Defaults are the ONE approved model::

    nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16  via  deepinfra

(2026-09: switched from Nemotron 3.5 Lightning / fireworks-ai — the HF
account can't enable pay-as-you-go there (HTTP 402) and deepinfra is the
only provider serving the Ultra BF16 build. ``reasoning_effort`` is a
deepinfra extension, so the narrator's no-think hint is honored natively.)

Env overrides (never commit values — see ``.env.example``)::

    WR_MODEL     model id (default: Nemotron 3 Ultra 550B)
    WR_PROVIDER  Inference Providers provider (default: deepinfra)
    WR_BASE_URL  if set, use an OpenAI-compatible endpoint instead of a
                 provider (e.g. local Ollama/NIM); token falls back to "no-key"
    HF_TOKEN     Inference Providers token (also accepted as an arg)

No Qwen references anywhere in this module by design.
"""

from __future__ import annotations

import os
from typing import Any

from huggingface_hub import InferenceClient

DEFAULT_MODEL = "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16"
DEFAULT_PROVIDER = "deepinfra"

ENV_MODEL = "WR_MODEL"
ENV_PROVIDER = "WR_PROVIDER"
ENV_BASE_URL = "WR_BASE_URL"
ENV_TOKEN = "HF_TOKEN"


def get_model_id() -> str:
    """Model id from ``WR_MODEL`` or the Nemotron Ultra default."""
    return os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL


def get_provider() -> str:
    """Inference Providers provider from ``WR_PROVIDER`` (default deepinfra)."""
    return os.environ.get(ENV_PROVIDER, "").strip() or DEFAULT_PROVIDER


def get_base_url() -> str | None:
    """OpenAI-compatible base URL from ``WR_BASE_URL`` (None = use provider)."""
    return os.environ.get(ENV_BASE_URL, "").strip() or None


def resolve_token(hf_token: str | None = None) -> str:
    """Token priority: explicit arg > ``HF_TOKEN`` env > ``""`` (unauthenticated)."""
    return (hf_token or "").strip() or os.environ.get(ENV_TOKEN, "").strip() or ""


def has_token(hf_token: str | None = None) -> bool:
    """True when a token is available without ever revealing it."""
    return bool(resolve_token(hf_token))


def get_client(hf_token: str | None = None) -> InferenceClient:
    """Build the single shared ``InferenceClient``.

    When ``WR_BASE_URL`` is set, returns an OpenAI-compatible client pointed
    at that URL (for local Ollama/NIM). Otherwise returns a provider-routed
    client for Nemotron Ultra on deepinfra.
    """
    token = resolve_token(hf_token)
    base_url = get_base_url()
    if base_url:
        return InferenceClient(base_url=base_url, api_key=token or "no-key")
    return InferenceClient(provider=get_provider(), api_key=token or None)


def build_agent_model(
    hf_token: str | None = None,
    max_tokens: int = 700,
    temperature: float = 0.2,
    timeout: int = 120,
) -> Any:
    """Build the smolagents ``InferenceClientModel`` for the agent.

    Same env resolution as :func:`get_client`; ``WR_BASE_URL`` maps to the
    model's ``base_url`` (OpenAI-compatible path), otherwise provider routing
    is used. Import is lazy so ``wavereader.llm`` stays importable without
    smolagents installed.
    """
    from smolagents import InferenceClientModel

    token = resolve_token(hf_token) or None
    base_url = get_base_url()
    kwargs: dict[str, Any] = {
        "model_id": get_model_id(),
        "token": token,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    if base_url:
        kwargs["base_url"] = base_url
    else:
        kwargs["provider"] = get_provider()
    return InferenceClientModel(**kwargs)


def smoke_test(hf_token: str | None = None, max_tokens: int = 50) -> dict:
    """One tiny live call proving Nemotron Ultra tool-calling path works.

    Costs a fraction of a cent (<=50 completion tokens). Returns
    ``{"ok": True, ...}`` on success or ``{"ok": False, "reason": ...}``
    when skipped/failed — callers must treat ``ok=False`` as "keep the
    ``WR_AGENT=code`` fallback", never as fatal.
    """
    if not has_token(hf_token):
        return {"ok": False, "reason": "no HF_TOKEN available; skipped live check"}
    client = get_client(hf_token)
    try:
        completion = client.chat.completions.create(
            model=get_model_id(),
            messages=[{"role": "user", "content": "Reply with exactly: ok"}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        text = completion.choices[0].message.content or ""
        usage = getattr(completion, "usage", None)
        return {
            "ok": True,
            "model": get_model_id(),
            "provider": get_provider(),
            "base_url": get_base_url(),
            "reply": text.strip()[:200],
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }
    except Exception as exc:  # noqa: BLE001 — report, don't raise
        return {
            "ok": False,
            "reason": f"{type(exc).__name__}: {exc}",
            "model": get_model_id(),
            "provider": get_provider(),
        }
