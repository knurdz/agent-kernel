"""Chat model selection for AgriPilot.

Picks the LLM provider based on which API key is present in the
environment. If several are set, the precedence is OpenAI, then Gemini,
then OpenRouter. Set the provider explicitly with
AGRIPILOT_MODEL_PROVIDER=openai|gemini|openrouter to override.
Set AGRIPILOT_OPENAI_MODEL / AGRIPILOT_GEMINI_MODEL /
AGRIPILOT_OPENROUTER_MODEL to override the default model name for that
provider.

OpenRouter uses the OpenAI-compatible endpoint; `openrouter/free` is the
Free Models Router, which picks a free model per request and filters for
the capabilities the request needs (tool calling included). Free-tier
accounts are limited to 20 requests/minute and 50 requests/day.

`get_judge_model` (narration-judge backstop) shares this provider logic
but can be pointed at a different provider via AGRIPILOT_JUDGE_PROVIDER
and a different model via AGRIPILOT_JUDGE_MODEL.
"""

import os
from typing import Optional

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _build_model(provider: str, model_name: Optional[str], temperature: float = 0.0):
    """Build a chat model for an explicit provider.

    :param provider: "openai" | "gemini" | "openrouter".
    :param model_name: Model override; None falls back to that provider's
        AGRIPILOT_<PROVIDER>_MODEL env var or built-in default.
    :raises ValueError: If provider is unknown.
    :raises RuntimeError: If the provider has no API key set.
    """
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name or os.environ.get("AGRIPILOT_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL,
            temperature=temperature,
        )

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name or os.environ.get("AGRIPILOT_GEMINI_MODEL") or DEFAULT_GEMINI_MODEL,
            temperature=temperature,
            google_api_key=os.environ.get("GEMINI_API_KEY"),
        )

    if provider == "openrouter":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name or os.environ.get("AGRIPILOT_OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL,
            temperature=temperature,
            base_url=OPENROUTER_BASE_URL,
            api_key=os.environ.get("OPENROUTER_API_KEY"),
        )

    raise ValueError(f"Unknown model provider: {provider!r} (expected openai, gemini, or openrouter)")


def _select_provider() -> str:
    """Pick a provider by explicit override or by whichever API key exists."""
    forced = os.environ.get("AGRIPILOT_MODEL_PROVIDER", "").lower()
    if forced:
        if forced not in ("openai", "gemini", "openrouter"):
            raise ValueError(f"Unknown AGRIPILOT_MODEL_PROVIDER: {forced!r}")
        # _build_model raises a clear error when the matching key is absent.
        return forced
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    raise RuntimeError(
        "No model credentials found. Set OPENAI_API_KEY, GEMINI_API_KEY, "
        "or OPENROUTER_API_KEY (see .env.local.example)."
    )


def get_chat_model(temperature: float = 0.0):
    """Return a chat model instance for whichever provider has credentials."""
    return _build_model(_select_provider(), None, temperature)


def get_judge_model(temperature: float = 0.0):
    """Return a chat model for the narration judge.

    Defaults to the same provider selection as `get_chat_model`, but can
    run on a different provider/model entirely:

    - ``AGRIPILOT_JUDGE_PROVIDER=openai|gemini|openrouter`` forces one
      (falls back to normal precedence when unset).
    - ``AGRIPILOT_JUDGE_MODEL`` overrides that provider's default name.
    """
    forced = os.environ.get("AGRIPILOT_JUDGE_PROVIDER", "").lower()
    if forced:
        if forced not in ("openai", "gemini", "openrouter"):
            raise ValueError(f"Unknown AGRIPILOT_JUDGE_PROVIDER: {forced!r}")
        provider = forced
    else:
        provider = _select_provider()
    return _build_model(provider, os.environ.get("AGRIPILOT_JUDGE_MODEL") or None, temperature)
