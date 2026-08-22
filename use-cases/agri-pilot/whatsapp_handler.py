"""Fast-ack WhatsApp webhook handler with message-ID deduplication.

The stock AgentWhatsAppRequestHandler awaits the full agent run inside the
webhook POST and only then returns 200. Meta's Cloud API times a webhook out
after ~10 s and redelivers — every redelivery re-ran the agent and sent
another reply (visible as repeated 2a03:2880:* POSTs in the access log).
This subclass returns 200 immediately after verifying the signature and
registering the incoming message IDs, then processes each new message as a
background asyncio task. Already-seen IDs are dropped, so late redeliveries
are ignored even if they slip past the timeout window.
"""

import asyncio
import logging
from collections import OrderedDict

from agentkernel.whatsapp import AgentWhatsAppRequestHandler
from fastapi import HTTPException, Request


class FastAckWhatsAppHandler(AgentWhatsAppRequestHandler):
    """Deduplicates deliveries and acknowledges Meta before processing."""

    _SEEN_LIMIT = 1024

    def __init__(self):
        super().__init__()
        self._log = logging.getLogger("agripilot.whatsapp")
        self._seen_ids: OrderedDict[str, None] = OrderedDict()

    def _mark_and_filter(self, body: dict) -> list[tuple[dict, dict]]:
        """Return unseen (message, value) pairs from the payload, marking them seen.

        Runs without awaits, so concurrent webhook deliveries cannot race past
        the check: within one event loop turn an ID is either registered or not.
        """
        pending: list[tuple[dict, dict]] = []
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for message in value.get("messages", []):
                    message_id = message.get("id")
                    if not message_id or message_id in self._seen_ids:
                        continue
                    self._seen_ids[message_id] = None
                    self._seen_ids.move_to_end(message_id)
                    while len(self._seen_ids) > self._SEEN_LIMIT:
                        self._seen_ids.popitem(last=False)
                    pending.append((message, value))
        return pending

    async def _handle_webhook(self, request: Request) -> dict:
        if self._app_secret:
            signature = request.headers.get("x-hub-signature-256", "")
            if not self._verify_signature(await request.body(), signature):
                self._log.warning("Invalid request signature")
                raise HTTPException(status_code=403, detail="Invalid signature")

        body = await request.json()
        if body.get("object") != "whatsapp_business_account":
            return {"status": "ok"}

        pending = self._mark_and_filter(body)
        for message, value in pending:
            asyncio.create_task(self._process_message(message, value))
        return {"status": "ok"}

    async def _process_message(self, message: dict, value: dict) -> None:
        try:
            await self._handle_message(message, value)
        except Exception:  # noqa: BLE001 - background task must never crash the server
            self._log.exception(f"Background processing failed for message {message.get('id')}")
