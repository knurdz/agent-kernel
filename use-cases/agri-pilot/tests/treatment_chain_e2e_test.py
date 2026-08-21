"""End-to-end chain test for Increment 4.3 (treatment workflow).

Drives the full triage -> vision -> knowledge -> safety path through the
Agent Kernel Runtime, the same way demo.py / the Phase 12 REST API will
eventually do it. The CLI and REST /run endpoint don't carry attachments
yet, so this test talks to Runtime.run() with text + a synthetic image.

Requires:
- a real model credential (OPENAI_API_KEY or GEMINI_API_KEY)
- the vision classifier weights (downloads on first run)

Marked `slow` alongside tests/vision_multimodal_test.py so it is skipped by
`pytest -m "not slow"`.
"""

import base64
import io
import re

import numpy as np
import pytest
from agentkernel.core.base import Session
from agentkernel.core.model import AgentRequestImage, AgentRequestText
from agentkernel.core.runtime import Runtime
from PIL import Image

import demo  # noqa: F401  - importing registers agents with the Runtime
from tools.safety_tool import known_chemical_names, known_dosage_units, validate_treatment

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CHEMICAL_NAMES = known_chemical_names()
_DOSAGE_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*(?:" + "|".join(re.escape(u) for u in known_dosage_units()) + r")",
    re.IGNORECASE,
)


def _sample_image_b64() -> str:
    arr = np.zeros((224, 224, 3), dtype=np.uint8)
    arr[..., 1] = 160
    arr[::8, :, :] = 40
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _chemical_dosage_pairs(text: str):
    """Yield (chemical_name, dosage_float) for each known chemical + nearest dose.

    Only used to assert the safety property, not to drive decisions.
    """
    lowered = text.lower()
    for name in _CHEMICAL_NAMES:
        for m in re.finditer(rf"\b{re.escape(name)}\b", lowered):
            end = m.end()
            dose_match = _DOSAGE_PATTERN.search(lowered, end)
            window = lowered[end : end + 30]
            dose_nearby = _DOSAGE_PATTERN.search(window)
            if dose_nearby:
                number = dose_nearby.group(0)
                value = float(re.match(r"\d+(?:\.\d+)?", number).group(0))
                yield name, value


@pytest.mark.slow
async def test_full_chain_produces_safety_validated_reply():
    """Increment 4.3: diagnosis -> RAG -> safety, all in one reply.

    The safety property asserted here is the increment's core: every
    chemical+dosage pair that reaches the farmer must NOT have been
    rejected by `validate_treatment`. Unknown chemicals / escalations are
    allowed in the reply text only when no dosage is co-stated; a
    rejected dosage must never appear alongside its chemical.
    """
    runtime = Runtime.current()
    agent = runtime.agents()["triage"]
    session = Session(id="treatment-workflow-e2e")

    requests = [
        AgentRequestText(prompt="My tomato leaves have spots. How should I treat it?"),
        AgentRequestImage(image_data=_sample_image_b64(), name="leaf.png", mime_type="image/png"),
    ]

    reply = await runtime.run(agent, session, requests)

    assert reply.prompt
    text = reply.prompt if isinstance(reply.prompt, str) else " ".join(str(p) for p in reply.prompt)

    # The reply must actually engage with the request (not a generic redirect).
    assert any(
        tok in text.lower()
        for tok in ("tomato", "leaf", "fungicide", "treat", "disease", "cannot safely recommend", "not enough verified")
    )

    # Core safety property: no rejected chemical+dosage pair reaches the farmer.
    for chemical, dosage in _chemical_dosage_pairs(text):
        verdict = validate_treatment(chemical=chemical, dosage=dosage, unit="g/L")["verdict"]
        assert (
            verdict != "reject"
        ), f"Reply stated {chemical!r} at {dosage} g/L, which the safety tool rejects: {text!r}"
