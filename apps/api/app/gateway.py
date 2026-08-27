"""Multi-model gateway, built on LiteLLM.

One interface across Anthropic / OpenAI / Google / DeepSeek so the rest of
the app (and the frontend's model picker) never talks to a provider SDK
directly. Centralizing routing here is deliberate — see the architecture
blueprint's note on avoiding gateway lock-in.

This module is wired but inert until Fase 0 (API budget) lands: calling
`complete()` for a provider with no key configured raises a clear
`ModelNotConfiguredError` rather than failing deep inside a request.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import get_settings


class ModelNotConfiguredError(RuntimeError):
    """Raised when a model provider is requested but has no API key set."""


# Maps our own short model ids (what the frontend's selector cycles through)
# to the litellm model string and the settings field holding its key.
MODEL_MAP: dict[str, tuple[str, str]] = {
    "claude": ("anthropic/claude-sonnet-4-5", "anthropic_api_key"),
    "gpt": ("openai/gpt-4.1", "openai_api_key"),
    "gemini": ("gemini/gemini-2.0-flash", "google_api_key"),
    "deepseek": ("deepseek/deepseek-chat", "deepseek_api_key"),
}


@dataclass
class CompletionRequest:
    model: str  # one of MODEL_MAP's keys
    messages: list[dict]
    stream: bool = True


def _require_key(model: str) -> tuple[str, str]:
    if model not in MODEL_MAP:
        raise ValueError(f"Unknown model id: {model!r}. Known: {list(MODEL_MAP)}")
    litellm_model, key_field = MODEL_MAP[model]
    key = getattr(get_settings(), key_field)
    if not key:
        raise ModelNotConfiguredError(
            f"No API key configured for {model!r} (expected {key_field.upper()} "
            "in the environment). This is expected pre-Fase-0 — see README."
        )
    return litellm_model, key


async def complete(request: CompletionRequest):
    """Route a completion request to the right provider via LiteLLM.

    Deliberately not implemented beyond the key check yet — the actual
    `litellm.acompletion(...)` call is Fase 1 work, gated on Fase 0 budget.
    """
    litellm_model, _key = _require_key(request.model)
    raise NotImplementedError(
        f"Gateway wiring for {litellm_model!r} lands with Fase 0 (model API budget)."
    )
