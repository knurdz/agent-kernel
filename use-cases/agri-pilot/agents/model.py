"""Chat model selection for AgriPilot.

Picks the LLM provider based on which API key is present in the
environment. If both are set, OpenAI is preferred. Set the provider
explicitly with AGRIPILOT_MODEL_PROVIDER=openai|gemini to override.
Set AGRIPILOT_OPENAI_MODEL / AGRIPILOT_GEMINI_MODEL to override the
default model name for that provider.
"""

import os

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


def get_chat_model(temperature: float = 0.0):
    """Return a chat model instance for whichever provider has credentials."""
    provider = os.environ.get("AGRIPILOT_MODEL_PROVIDER", "").lower()

    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))

    if provider == "openai" or (not provider and has_openai):
        from langchain_openai import ChatOpenAI

        model_name = os.environ.get("AGRIPILOT_OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
        return ChatOpenAI(model=model_name, temperature=temperature)

    if provider == "gemini" or (not provider and has_gemini):
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = os.environ.get("AGRIPILOT_GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        return ChatGoogleGenerativeAI(
            model=model_name, temperature=temperature, google_api_key=os.environ.get("GEMINI_API_KEY")
        )

    raise RuntimeError(
        "No model credentials found. Set OPENAI_API_KEY or GEMINI_API_KEY "
        "(see .env.local.example)."
    )
