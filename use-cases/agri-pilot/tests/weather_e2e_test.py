"""Live-LLM integration tests for the resource workflow (Increments 5.2, 5.3).

Drives the full triage -> resource path through the Agent Kernel Runtime,
the same way demo.py / the Phase 12 REST API do it.

Requires a real model credential (OPENAI_API_KEY or GEMINI_API_KEY).
Marked `slow` so it is skipped by `pytest -m "not slow"`.

The OpenAI input/output moderation guardrails are disabled via env override
(read by AKConfig before its first access) so running these tests does not
consume OpenAI-guardrail credits; the chat model itself still needs credits.
"""

import os

os.environ.setdefault("AK_GUARDRAIL__INPUT__ENABLED", "false")
os.environ.setdefault("AK_GUARDRAIL__OUTPUT__ENABLED", "false")

import pytest
from agentkernel.core.base import Session
from agentkernel.core.model import AgentRequestText
from agentkernel.core.runtime import Runtime

import demo  # noqa: F401  - importing registers agents with the Runtime

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _run(session_id: str, prompt: str) -> str:
    runtime = Runtime.current()
    agent = runtime.agents()["triage"]
    session = Session(id=session_id)
    reply = await runtime.run(agent, session, [AgentRequestText(prompt=prompt)])
    # AgentReplyText.prompt echoes the request; the answer is in .response.
    return reply.response or reply.prompt


@pytest.mark.slow
async def test_irrigation_reply_cites_a_forecast_value():
    """Increment 5.2: 'Should I water...' must cite a concrete forecast number."""
    text = await _run(
        "irrigation-e2e",
        "My location is Kandy. I have tomato plants in flowering stage. " "Should I water my tomato plants today?",
    )
    assert "%" in text or any(tok in text.lower() for tok in ("mm", "°c", "chance of rain", "temperature"))


@pytest.mark.slow
async def test_spray_timing_gives_one_of_three_outcomes_with_reason():
    """Increment 5.3: 'Can I spray tomorrow?' must yield suitable / not
    suitable / cannot determine, with a reason."""
    text = await _run(
        "spray-timing-e2e",
        "My location is Kandy. My tomato plants were diagnosed with early blight. "
        "I plan to spray a fungicide tomorrow — can I spray tomorrow?",
    )
    lowered = text.lower()
    outcome = any(v in lowered for v in ("suitable", "cannot determine"))
    assert outcome, f"Reply gave no spray-timing outcome: {text!r}"
    assert len(text) > len("suitable"), "Outcome must come with a reason."
