"""Integration test for the Increment 4.2 OpenAI guardrail configuration.

Verifies the config.yaml `guardrail` block is well-formed and that
AgentKernel's factories build real `OpenAIInputGuardrail` /
`OpenAIOutputGuardrail` instances from it -- catching config typos
(wrong field names, missing config_path/model) without needing a real
OpenAI API call.
"""

import os

from agentkernel.core.config import AKConfig
from agentkernel.guardrail.guardrail import InputGuardrailFactory, OutputGuardrailFactory
from agentkernel.guardrail.openai import OpenAIInputGuardrail, OpenAIOutputGuardrail

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _reload_config():
    """Force AKConfig to reload config.yaml from the project root.

    Temporarily strips `AK_GUARDRAIL__*` env overrides: `.env.local` sets
    AK_GUARDRAIL__INPUT/OUTPUT__ENABLED=false for zero-cost local runs, and
    any test module importing demo (which calls load_dotenv) leaks those
    into os.environ at collection time -- where they would otherwise take
    priority over config.yaml inside this test.
    """
    saved = {key: os.environ.pop(key) for key in list(os.environ) if key.startswith("AK_GUARDRAIL__")}
    try:
        os.chdir(PROJECT_ROOT)
        AKConfig._reset()
        return AKConfig.get()
    finally:
        os.environ.update(saved)


def test_input_guardrail_config_is_enabled_and_openai_typed():
    config = _reload_config().guardrail.input
    assert config.enabled is True
    assert config.type == "openai"
    assert config.model == "gpt-4o-mini"
    assert config.config_path == "guardrails_input.json"


def test_output_guardrail_config_is_enabled_and_openai_typed():
    config = _reload_config().guardrail.output
    assert config.enabled is True
    assert config.type == "openai"
    assert config.model == "gpt-4o-mini"
    assert config.config_path == "guardrails_output.json"


def test_input_guardrail_factory_builds_openai_guardrail():
    _reload_config()
    guardrail = InputGuardrailFactory.get()
    assert isinstance(guardrail, OpenAIInputGuardrail)
    assert guardrail.name() == "OpenAIInputGuardrail"


def test_output_guardrail_factory_builds_openai_guardrail():
    _reload_config()
    guardrail = OutputGuardrailFactory.get()
    assert isinstance(guardrail, OpenAIOutputGuardrail)
    assert guardrail.name() == "OpenAIOutputGuardrail"
