"""Multimodal integration test for the vision agent (Increments 2.3, 2.5).

Talks directly to the Agent Kernel Runtime with a text+image request. The
CLI (demo.py) only accepts text over stdin, and the REST API's /run
endpoint doesn't exist until Phase 12, so neither surface can carry an
image attachment yet. This test drives the same Runtime.run() path they
will eventually call.
"""

import base64
import io

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


@pytest.mark.slow
async def test_vision_agent_describes_attached_image():
    """Increment 2.3 test: text + image in, and the agent engages with it."""
    runtime = Runtime.current()
    agent = runtime.agents()["triage"]
    session = Session(id="vision-multimodal-test")

    requests = [
        AgentRequestText(prompt="My tomato leaves have spots. What should I do?"),
        AgentRequestImage(image_data=_sample_image_b64(), name="leaf.png", mime_type="image/png"),
    ]

    reply = await runtime.run(agent, session, requests)

    assert reply.prompt
