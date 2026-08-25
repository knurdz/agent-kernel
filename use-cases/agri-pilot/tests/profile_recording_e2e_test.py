"""Live-LLM integration test for farmer-profile recording (Phase 7.2).

Completes one full diagnosis turn (vision -> knowledge chain) through the
Agent Kernel Runtime, then asserts the durable profile gained a case
record — the Phase 7.2 test: "Complete one diagnosis. Confirm the profile
fields are present in storage afterward."

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
from state.farmer_profile import CASE_OPEN, CaseRecord, get_farmer_profile

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _sample_image_b64() -> str:
    arr = np.zeros((224, 224, 3), dtype=np.uint8)
    arr[..., 1] = 160
    arr[::8, :, :] = 40
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.mark.slow
async def test_completed_diagnosis_is_recorded_in_the_profile():
    runtime = Runtime.current()
    agent = runtime.agents()["triage"]
    session_id = f"profile-recording-e2e-{os.getpid()}"
    session = Session(id=session_id)

    await runtime.run(
        agent,
        session,
        [
            AgentRequestText(
                prompt="My location is Kandy. My tomato leaves have spots — what is wrong and what should I do?"
            ),
            AgentRequestImage(image_data=_sample_image_b64(), name="leaf.png", mime_type="image/png"),
        ],
    )

    persisted = Runtime.current().sessions().load(session_id)
    profile = get_farmer_profile(persisted)
    assert profile.cases, f"No case was recorded after a completed diagnosis: {profile.to_dict()}"

    tomato_cases = [case for case in profile.cases if case.crop == "tomato"]
    assert tomato_cases, f"Case history has no tomato episode: {profile.to_dict()}"
    case = tomato_cases[-1]
    assert isinstance(case, CaseRecord)
    assert case.date, "Case record must carry the interaction date"
    assert case.follow_up_status == CASE_OPEN
    assert isinstance(case.disease, str) and case.disease, f"A completed diagnosis must record the disease name: {case}"
