"""Live-LLM integration test for conversation continuity (Phase 7.3).

Replays the architecture doc's Day 1 / Day 3 example against the real
Runtime on one session: a diagnosis turn, then "it is getting worse" two
days later. The Day 3 reply must build on the stored case — referencing
the earlier diagnosis or advice — without asking the farmer to resend a
photo or restate the crop.

Requires a real model credential (OPENAI_API_KEY or GEMINI_API_KEY).
Marked `slow` so it is skipped by `pytest -m "not slow"`.
"""

import base64
import io
import os

os.environ.setdefault("AK_GUARDRAIL__INPUT__ENABLED", "false")
os.environ.setdefault("AK_GUARDRAIL__OUTPUT__ENABLED", "false")

import numpy as np
import pytest
from agentkernel.core.base import Session
from agentkernel.core.model import AgentRequestImage, AgentRequestText
from agentkernel.core.runtime import Runtime
from PIL import Image

import demo  # noqa: F401  - importing registers agents with the Runtime

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _sample_image_b64() -> str:
    arr = np.zeros((224, 224, 3), dtype=np.uint8)
    arr[..., 1] = 160
    arr[::8, :, :] = 40
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


async def _run(session_id: str, requests: list) -> str:
    runtime = Runtime.current()
    agent = runtime.agents()["triage"]
    reply = await runtime.run(agent, Session(id=session_id), requests)
    return reply.response or reply.prompt


@pytest.mark.slow
async def test_day3_followup_references_day1_diagnosis_without_reasking():
    session_id = f"memory-continuity-e2e-{os.getpid()}"

    day1 = await _run(
        session_id,
        [
            AgentRequestText(prompt="My tomato leaves have dark spots. What is wrong and what should I do?"),
            AgentRequestImage(image_data=_sample_image_b64(), name="leaf.png", mime_type="image/png"),
        ],
    )
    assert day1, "Day 1 produced no reply"

    day3 = await _run(session_id, [AgentRequestText(prompt="It is getting worse. What should I do now?")])
    lowered = day3.lower()

    # Must not treat it as a brand-new request.
    for reask in ("send a photo", "please send", "which crop", "what crop"):
        assert reask not in lowered, f"Day 3 asked the farmer to repeat themselves: {day3!r}"

    # Must engage with the stored case: name the crop, or give follow-up
    # treatment guidance that only makes sense against the Day 1 diagnosis.
    engages = "tomato" in lowered or any(
        term in lowered for term in ("blight", "spot", "lesion", "treatment", "spray", "fungicide", "leaf")
    )
    assert engages, f"Day 3 reply does not reference the Day 1 case: {day3!r}"
