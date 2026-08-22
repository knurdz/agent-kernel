"""Attachment resolution for AgriPilot vision tools.

Agent Kernel's MultimodalPreHook strips raw image bytes from incoming
requests and injects only "[Attached Images/Files:]" metadata (attachment ID
plus a one-line description) into the prompt. AgriPilot's vision tools take a
filesystem path, so the agent needs a way to turn a listed attachment ID back
into a readable file before calling check_image_quality / diagnose_crop_image.
"""

import base64
import logging
from typing import Any

log = logging.getLogger("agripilot.attachment")

_MIME_SUFFIXES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _session_id() -> str | None:
    try:
        from agentkernel.core.tool import ToolContext

        return ToolContext.get().session.id
    except Exception:  # noqa: BLE001 - outside an agent run there is no session
        return None


def get_attachment_path(attachment_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Materialize a stored Agent Kernel attachment as a local temp file.

    Call this with an attachment ID from the "[Attached Images/Files:]" list
    in the farmer's message before using check_image_quality or
    diagnose_crop_image on it. Never pass the attachment ID itself as an
    image path.

    :param attachment_id: Attachment ID listed in the current message.
    :param session_id: Optional session override; leave unset inside an
        agent run (the active session is detected automatically).
    :return: {"ok": True, "path": <local file>} on success, or
        {"ok": False, "path": None, "reason": <why>} otherwise.
    """
    from agentkernel.core.multimodal.storage.storage_manager import AttachmentStorageManager

    sid = session_id or _session_id()
    if not sid or not attachment_id:
        return {"ok": False, "path": None, "reason": "No active session or attachment ID."}

    attachments = AttachmentStorageManager(session_id=sid).get_attachment_data([attachment_id])
    if not attachments:
        return {"ok": False, "path": None, "reason": f"No attachment '{attachment_id}' found in this session."}

    att = attachments[0]
    if att.type != "image":
        return {"ok": False, "path": None, "reason": f"Attachment '{attachment_id}' is {att.type}, not an image."}

    import tempfile

    suffix = _MIME_SUFFIXES.get(att.mime_type.lower(), ".bin")
    handle = tempfile.NamedTemporaryFile(prefix="ak_attach_", suffix=suffix, delete=False)
    try:
        handle.write(base64.b64decode(att.data))
    except Exception as exc:  # noqa: BLE001 - corrupt payload means unreadable image
        log.error(f"Failed to decode attachment {attachment_id}: {exc}")
        return {"ok": False, "path": None, "reason": "The attached image data could not be decoded."}
    finally:
        handle.close()

    log.info(f"Materialized attachment {attachment_id} as {handle.name}")
    return {"ok": True, "path": handle.name}
