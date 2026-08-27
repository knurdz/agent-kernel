"""Shared channel chat execution with unified user sessions."""

from __future__ import annotations

import traceback
from typing import TYPE_CHECKING, Any, List, Optional

from agentkernel.core.model import AgentRequest, BaseChatRequest

from marketplace.session_identity import canonical_session_id, seed_marketplace_session

if TYPE_CHECKING:
    from marketplace.models import User


async def execute_channel_chat(
    handler: Any,
    *,
    user: User,
    prompt: str,
    requests: List[AgentRequest],
    reply_to: Any,
    send_error,
) -> None:
    """Run agent chat with canonical session id and seeded marketplace identity."""
    session_id = canonical_session_id(user.id)
    user_id = str(user.id)
    try:
        ack = getattr(handler, "_whatsapp_agent_acknowledgement", None)
        if ack and hasattr(handler, "_send_message"):
            await handler._send_message(reply_to, ack, getattr(handler, "_last_message_id", None))

        req = BaseChatRequest(
            prompt=prompt,
            agent=getattr(handler, "_whatsapp_agent", None) or getattr(handler, "_telegram_agent", "triage"),
            session_id=session_id,
            user_id=user_id,
        )
        try:
            result, loaded_session_id = await handler._chat_service.execute(req, requests=requests)
        except ValueError as ve:
            handler._log.warning("Agent execution rejected: %s (session_id: %s)", ve, session_id)
            await send_error("Sorry, no agent is available to handle your request.")
            return

        # Seed marketplace KV on the persisted session (best-effort; tools read on next get).
        try:
            from agentkernel.core.base import Session
            from agentkernel.core.runtime import Runtime

            runtime = Runtime.current()
            store = runtime.sessions()
            session = store.load(loaded_session_id or session_id)
            if session is not None:
                seed_marketplace_session(session, user)
                await store.store(session)
        except Exception:
            handler._log.debug("session seed skipped", exc_info=True)

        response_text = str(result)
        handler._log.debug("Agent response: %s", response_text[:200])
        await handler._send_message(reply_to, response_text, getattr(handler, "_last_message_id", None))
    except Exception as exc:  # noqa: BLE001
        handler._log.error("Error handling message: %s\n%s", exc, traceback.format_exc())
        await send_error("Sorry, there was an error processing your request.")
