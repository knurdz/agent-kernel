"""Unit tests for the attachment resolver tool (Phase 8 image fix).

The WhatsApp path delivers images as Agent Kernel attachments; the vision
tools need real files. get_attachment_path must bridge the two without any
LLM or network involvement, so these tests are not marked slow.
"""

import base64
import io

from agentkernel.core.multimodal.storage.storage_manager import AttachmentStorageManager
from PIL import Image

from tools.attachment_tool import get_attachment_path


def _tiny_png_b64() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(40, 120, 30)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_resolves_saved_attachment_to_readable_file():
    manager = AttachmentStorageManager(session_id="att-test-session")
    att_id = manager.save_attachment(
        data=_tiny_png_b64(),
        attachment_type="image",
        name="leaf.png",
        mime_type="image/png",
    )

    result = get_attachment_path(att_id, session_id="att-test-session")

    assert result["ok"] is True
    with Image.open(result["path"]) as image:
        assert image.format == "PNG"


def test_unknown_attachment_reports_failure():
    result = get_attachment_path("00000000-0000-0000-0000-000000000000", session_id="att-test-session")
    assert result["ok"] is False
    assert "No attachment" in result["reason"]
