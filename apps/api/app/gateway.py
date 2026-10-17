"""Multi-model gateway, built on LiteLLM.

One interface across Anthropic / OpenAI / Google / DeepSeek so the rest of
the app (and the frontend's model picker) never talks to a provider SDK
directly. Centralizing routing here is deliberate — see the architecture
blueprint's note on avoiding gateway lock-in.

The routing and streaming logic below is real — it's the same code that
runs once Fase 0 (API budget) lands. What's still absent is the budget
itself: calling `complete()` for a provider with no key configured raises
a clear `ModelNotConfiguredError` rather than failing deep inside a
request, or worse, faking a response. Writing this for real now (instead
of leaving it as a stub) costs nothing — it only executes a network call
when a key is actually present, and none are.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.config import get_settings


class ModelNotConfiguredError(RuntimeError):
    """Raised when a model provider is requested but has no API key set."""


def _litellm():
    # Imported on use: LiteLLM is large and only this legacy (household-less)
    # chat path needs it, so the Vercel deployment leaves it out
    # (requirements-extras.txt).
    try:
        import litellm
    except ImportError as exc:
        raise ModelNotConfiguredError(
            "LiteLLM isn't installed on this server (requirements-extras.txt), so this chat path is off."
        ) from exc
    return litellm


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


async def complete(request: CompletionRequest) -> str:
    """Non-streaming completion. Raises ModelNotConfiguredError pre-Fase-0."""
    litellm_model, api_key = _require_key(request.model)
    response = await _litellm().acompletion(
        model=litellm_model,
        messages=request.messages,
        api_key=api_key,
        stream=False,
    )
    return response.choices[0].message.content or ""


async def stream_complete(request: CompletionRequest) -> AsyncIterator[str]:
    """Streaming completion — yields content deltas as they arrive.
    Raises ModelNotConfiguredError immediately (before any network call)
    pre-Fase-0, same as `complete()`.
    """
    litellm_model, api_key = _require_key(request.model)
    response = await _litellm().acompletion(
        model=litellm_model,
        messages=request.messages,
        api_key=api_key,
        stream=True,
    )
    async for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
