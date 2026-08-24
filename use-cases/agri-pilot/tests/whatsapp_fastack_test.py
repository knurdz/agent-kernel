"""Tests for the fast-ack WhatsApp handler (duplicate-reply fix).

Meta redelivers webhooks when processing exceeds its timeout window; each
redelivery used to re-run the agent and send another reply. These tests pin
the two behaviors that stop that: background processing after an immediate
200, and message-ID deduplication across deliveries.
"""

import asyncio
import json
import logging
import os

for _var in ("AK_WHATSAPP__ACCESS_TOKEN", "AK_WHATSAPP__PHONE_NUMBER_ID"):
    os.environ.setdefault(_var, "dummy")

from starlette.requests import Request

from whatsapp_handler import FastAckWhatsAppHandler


def _webhook_payload(message_id: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {"id": message_id, "from": "15550001111", "type": "text", "text": {"body": "hello"}}
                            ],
                        },
                    }
                ],
            }
        ],
    }


def _post_request(payload: dict) -> Request:
    raw = json.dumps(payload).encode()
    scope = {"type": "http", "method": "POST", "path": "/whatsapp/webhook", "headers": [], "query_string": b""}

    async def receive():
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(scope, receive)


def _handler_with_recorder(processed: list) -> FastAckWhatsAppHandler:
    logging.getLogger("agripilot.whatsapp").setLevel(logging.ERROR)
    handler = FastAckWhatsAppHandler()
    # Fast-ack tests are not marketplace-gate tests — bypass WhatsApp subscription gate
    # (which would otherwise block unknown wa_id "15550001111" with signup URL)
    handler._skip_marketplace_gate = True  # type: ignore[attr-defined]
    # Other tests import demo, which load_dotenv()s .env.local; a real
    # APP_SECRET there would make the synthetic requests below fail
    # signature verification. Force it off for these tests.
    handler._app_secret = None

    async def record(message, value):
        await asyncio.sleep(0)
        processed.append(message["id"])

    handler._handle_message = record
    return handler


def test_redelivery_processed_once():
    processed: list = []
    handler = _handler_with_recorder(processed)

    async def scenario():
        first = await handler._handle_webhook(_post_request(_webhook_payload("wamid.A")))
        assert first == {"status": "ok"}
        second = await handler._handle_webhook(_post_request(_webhook_payload("wamid.A")))
        assert second == {"status": "ok"}
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    assert processed == ["wamid.A"]


def test_background_task_completes_processing():
    processed: list = []
    handler = _handler_with_recorder(processed)

    async def scenario():
        await handler._handle_webhook(_post_request(_webhook_payload("wamid.B")))
        assert processed == []  # ack returned before processing ran
        await asyncio.sleep(0.05)
        assert processed == ["wamid.B"]

    asyncio.run(scenario())


def test_seen_cache_evicts_oldest():
    processed: list = []
    handler = _handler_with_recorder(processed)
    handler._SEEN_LIMIT = 2

    payload_a = _webhook_payload("wamid.C")

    async def scenario():
        await handler._handle_webhook(_post_request(payload_a))
        await handler._handle_webhook(_post_request(_webhook_payload("wamid.D")))
        await handler._handle_webhook(_post_request(_webhook_payload("wamid.E")))

    asyncio.run(scenario())

    pending = handler._mark_and_filter(_webhook_payload("wamid.C"))
    assert [message["id"] for message, _ in pending] == ["wamid.C"]  # oldest was evicted
