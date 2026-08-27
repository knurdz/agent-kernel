"""Tests for the gated Telegram webhook handler (dedup half).

Telegram redelivers updates when the webhook does not answer 2xx quickly;
each redelivery would re-run the agent and send another reply. These tests
pin update-ID deduplication across deliveries and the update types it covers,
plus that the stock webhook route keeps acknowledging immediately.
"""

import asyncio
import logging
import os

for _var in ("AK_TELEGRAM__BOT_TOKEN",):
    os.environ.setdefault(_var, "dummy")

from fastapi import FastAPI
from starlette.testclient import TestClient

from telegram_handler import GatedTelegramHandler

CHAT_ID = 555001


def _message(text: str = "hello") -> dict:
    return {
        "message_id": 1,
        "date": 0,
        "chat": {"id": CHAT_ID, "type": "private"},
        "from": {"id": CHAT_ID, "is_bot": False},
        "text": text,
    }


def _update(update_id: int, kind: str = "message") -> dict:
    payload: dict = {"update_id": update_id}
    if kind == "edited_message":
        payload[kind] = {**_message("edited"), "edit_date": 1}
    elif kind == "callback_query":
        payload[kind] = {"id": f"cbq{update_id}", "data": "x", "message": _message()}
    else:
        payload[kind] = _message()
    return payload


def _handler_with_recorder(delegated: list) -> GatedTelegramHandler:
    logging.getLogger("agripilot.telegram").setLevel(logging.ERROR)
    handler = GatedTelegramHandler()
    # Dedup tests are not marketplace-gate tests — bypass the Telegram
    # subscription gate (which would otherwise block the synthetic chat).
    handler._skip_marketplace_gate = True  # type: ignore[attr-defined]
    # Route secret check is per-handler; clear it so the ack test doesn't
    # depend on env state left by other tests.
    handler._webhook_secret = None  # type: ignore[attr-defined]

    async def record(body: dict):
        await asyncio.sleep(0)
        delegated.append(body["update_id"])

    handler._delegate = record  # type: ignore[method-assign]
    return handler


def test_redelivery_processed_once():
    delegated: list = []
    handler = _handler_with_recorder(delegated)

    async def scenario():
        await handler._process_webhook_body(_update(101))
        await handler._process_webhook_body(_update(101))

    asyncio.run(scenario())
    assert delegated == [101]


def test_distinct_updates_both_processed():
    delegated: list = []
    handler = _handler_with_recorder(delegated)

    async def scenario():
        await handler._process_webhook_body(_update(102))
        await handler._process_webhook_body(_update(103))

    asyncio.run(scenario())
    assert sorted(delegated) == [102, 103]


def test_seen_cache_evicts_oldest():
    delegated: list = []
    handler = _handler_with_recorder(delegated)
    handler._SEEN_LIMIT = 2

    async def scenario():
        await handler._process_webhook_body(_update(201))
        await handler._process_webhook_body(_update(202))
        await handler._process_webhook_body(_update(203))  # evicts 201
        await handler._process_webhook_body(_update(202))  # still seen -> dropped
        await handler._process_webhook_body(_update(201))  # evicted -> reprocessed

    asyncio.run(scenario())
    # 202 was still inside the seen-set when re-delivered (dropped once);
    # 201 had been evicted by 203, so its redelivery is legitimately
    # reprocessed — the cache bounds memory, not the retry window.
    assert delegated == [201, 202, 203, 201]
    assert delegated.count(202) == 1


def test_edited_message_and_callback_deduped_by_update_id():
    delegated: list = []
    handler = _handler_with_recorder(delegated)

    async def scenario():
        await handler._process_webhook_body(_update(301, kind="edited_message"))
        await handler._process_webhook_body(_update(301, kind="edited_message"))
        await handler._process_webhook_body(_update(302, kind="callback_query"))
        await handler._process_webhook_body(_update(302, kind="callback_query"))
        await handler._process_webhook_body(_update(303, kind="callback_query"))

    asyncio.run(scenario())
    assert sorted(delegated) == [301, 302, 303]


def test_webhook_route_acks_before_processing():
    delegated: list = []
    handler = _handler_with_recorder(delegated)

    app = FastAPI()
    app.include_router(handler.get_router())

    with TestClient(app) as client:
        resp = client.post("/telegram/webhook", json=_update(401))
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert delegated == [401]


def test_webhook_secret_enforced_when_configured():
    delegated: list = []
    handler = _handler_with_recorder(delegated)
    handler._webhook_secret = "s3cret-token"

    app = FastAPI()
    app.include_router(handler.get_router())

    with TestClient(app) as client:
        denied = client.post("/telegram/webhook", json=_update(402))
        assert denied.status_code == 403
        allowed = client.post(
            "/telegram/webhook", json=_update(402), headers={"X-Telegram-Bot-Api-Secret-Token": "s3cret-token"}
        )
        assert allowed.status_code == 200
        assert delegated == [402]
