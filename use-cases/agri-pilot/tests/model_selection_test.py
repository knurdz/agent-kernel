"""Unit tests for agents/model.py provider selection (OpenRouter addition).

Pure selection-logic tests: constructing the LangChain model objects makes
no network calls, so these run fast and need no real credentials.
"""

import pytest

from agents.model import (
    DEFAULT_OPENROUTER_MODEL,
    OPENROUTER_BASE_URL,
    get_chat_model,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # OPENROUTER_API_KEY must be cleared too: slow-marked e2e modules do
    # `import demo` at collection time, and demo's load_dotenv(".env.local")
    # leaks real key values into os.environ for everything collected after.
    for var in (
        "AGRIPILOT_MODEL_PROVIDER",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "AGRIPILOT_OPENROUTER_MODEL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_openrouter_selected_when_only_openrouter_key_set(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    model = get_chat_model()
    assert type(model).__name__ == "ChatOpenAI"
    assert OPENROUTER_BASE_URL in str(model.openai_api_base)
    assert model.model_name == DEFAULT_OPENROUTER_MODEL


def test_explicit_provider_beats_precedence(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AGRIPILOT_MODEL_PROVIDER", "openrouter")

    model = get_chat_model()
    assert type(model).__name__ == "ChatOpenAI"
    assert OPENROUTER_BASE_URL in str(model.openai_api_base)


def test_precedence_openai_then_gemini_then_openrouter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    # OpenAI wins by default (existing behaviour preserved).
    assert get_chat_model().model_name.startswith("gpt")

    monkeypatch.delenv("OPENAI_API_KEY")
    # Gemini next.
    from langchain_google_genai import ChatGoogleGenerativeAI

    assert isinstance(get_chat_model(), ChatGoogleGenerativeAI)

    monkeypatch.delenv("GEMINI_API_KEY")
    # OpenRouter last.
    assert OPENROUTER_BASE_URL in str(get_chat_model().openai_api_base)


def test_openrouter_model_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("AGRIPILOT_OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    assert get_chat_model().model_name == "meta-llama/llama-3.3-70b-instruct:free"


def test_no_keys_raises_with_all_options_mentioned(monkeypatch):
    with pytest.raises(RuntimeError) as excinfo:
        get_chat_model()
    message = str(excinfo.value)
    for key in ("OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY"):
        assert key in message
