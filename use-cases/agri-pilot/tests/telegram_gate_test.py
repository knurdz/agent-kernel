"""Tests for the Telegram farmer-only subscription gate and contact-share linking.

Mirrors the WhatsApp hard gate semantics: only linked, active farmers reach
the agent; unlinked chats get a contact-share keyboard; non-farmers and
inactive subscriptions get the signup notice — never an LLM call.
"""

import asyncio
import logging
import os

for _var in ("AK_TELEGRAM__BOT_TOKEN",):
    os.environ.setdefault(_var, "dummy")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import marketplace.database as database_module
import marketplace.models  # noqa: F401  ensure tables registered
from marketplace.database import Base
from marketplace.models import User
from telegram_handler import GatedTelegramHandler

FARMER_PHONE = "+94770000401"
CHAT_ID = 555100


@pytest.fixture
def db_factory(monkeypatch):
    """In-memory user table, wired in as the handler's SessionLocal."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(database_module, "SessionLocal", factory)
    yield factory
    engine.dispose()


def _make_user(db, phone=FARMER_PHONE, **overrides) -> User:
    fields = dict(role="farmer", password_hash="hash", name="Amal", subscription_status="active")
    fields.update(overrides)
    user = User(phone_number=phone, **fields)
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def handler():
    logging.getLogger("agripilot.telegram").setLevel(logging.ERROR)
    h = GatedTelegramHandler()
    sent: list = []
    delegated: list = []

    async def fake_send(chat_id, text, parse_mode=None, reply_markup=None):
        await asyncio.sleep(0)
        sent.append((chat_id, text, reply_markup))

    async def fake_delegate(body: dict):
        await asyncio.sleep(0)
        delegated.append(body["update_id"])

    h._send_message = fake_send  # type: ignore[method-assign]
    h._delegate = fake_delegate  # type: ignore[method-assign]
    h.sent = sent  # type: ignore[attr-defined]
    h.delegated = delegated  # type: ignore[attr-defined]
    return h


def _text_update(update_id: int, text: str, chat_id: int = CHAT_ID) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False},
            "text": text,
        },
    }


def _contact_update(update_id: int, phone: str, contact_user_id=None, chat_id: int = CHAT_ID) -> dict:
    contact: dict = {"phone_number": phone}
    if contact_user_id is not None:
        contact["user_id"] = contact_user_id
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False},
            "contact": contact,
        },
    }


def _linked_chat_update(update_id: int, chat_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": 0,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "is_bot": False},
            "text": "hello",
        },
    }


def test_unlinked_chat_gets_link_prompt_not_agent(handler, db_factory):
    asyncio.run(handler._process_webhook_body(_text_update(1, "my tomato leaves are curling")))
    assert handler.delegated == []
    assert len(handler.sent) == 1
    _, text, markup = handler.sent[0]
    assert "farmer" in text
    keyboard = markup["keyboard"][0][0]
    assert keyboard["request_contact"] is True


def test_start_command_gets_link_prompt(handler, db_factory):
    asyncio.run(handler._process_webhook_body(_text_update(2, "/start")))
    assert handler.delegated == []
    assert handler.sent and handler.sent[0][2]["keyboard"][0][0]["request_contact"] is True


def test_contact_share_links_active_farmer(handler, db_factory):
    with db_factory() as db:
        _make_user(db)

    asyncio.run(handler._process_webhook_body(_contact_update(3, FARMER_PHONE, contact_user_id=CHAT_ID)))

    assert handler.delegated == []  # linking turn does not run the agent
    with db_factory() as db:
        row = db.get(User, 1)
        assert row.telegram_chat_id == CHAT_ID
    assert any("linked" in (text or "").lower() for _, text, _ in handler.sent)


def test_contact_share_links_when_telegram_omits_plus(handler, db_factory):
    """Real Telegram sends '94704512463' without '+'; must still link (captured 6024848)."""
    with db_factory() as db:
        _make_user(db)

    # No '+' prefix — exactly what /app logs showed: raw='94704512463'
    asyncio.run(handler._process_webhook_body(_contact_update(99, "94770000401", contact_user_id=CHAT_ID)))

    assert handler.delegated == []
    with db_factory() as db:
        row = db.get(User, 1)
        assert row.telegram_chat_id == CHAT_ID
    assert any("linked" in (text or "").lower() for _, text, _ in handler.sent)


def test_linked_farmer_reaches_agent(handler, db_factory):
    with db_factory() as db:
        _make_user(db, telegram_chat_id=CHAT_ID)

    asyncio.run(handler._process_webhook_body(_text_update(4, "what's wrong with my paddy?")))
    assert handler.delegated == [4]
    assert handler.sent == []


def test_forwarded_contact_user_id_mismatch_rejected(handler, db_factory):
    with db_factory() as db:
        _make_user(db)

    asyncio.run(handler._process_webhook_body(_contact_update(5, FARMER_PHONE, contact_user_id=999999)))
    with db_factory() as db:
        assert db.get(User, 1).telegram_chat_id is None
    assert handler.delegated == []


def test_buyer_role_blocked_at_linking(handler, db_factory):
    with db_factory() as db:
        _make_user(db, phone="+94770000402", role="buyer")

    asyncio.run(handler._process_webhook_body(_contact_update(6, "+94770000402", contact_user_id=CHAT_ID)))
    with db_factory() as db:
        assert db.get(User, 1).telegram_chat_id is None
    assert any("sign up" in (text or "").lower() for _, text, _ in handler.sent)


def test_expired_subscription_blocked_at_linking(handler, db_factory):
    with db_factory() as db:
        _make_user(db, subscription_status="expired")

    asyncio.run(handler._process_webhook_body(_contact_update(7, FARMER_PHONE, contact_user_id=CHAT_ID)))
    with db_factory() as db:
        assert db.get(User, 1).telegram_chat_id is None
    assert any("sign up" in (text or "").lower() for _, text, _ in handler.sent)


def test_phone_already_linked_to_other_chat_refused(handler, db_factory):
    other_chat = CHAT_ID + 1
    with db_factory() as db:
        _make_user(db, telegram_chat_id=other_chat)

    asyncio.run(handler._process_webhook_body(_contact_update(8, FARMER_PHONE, contact_user_id=CHAT_ID)))
    with db_factory() as db:
        row = db.get(User, 1)
        assert row.telegram_chat_id == other_chat  # untouched


def test_linked_but_inactive_blocked_before_agent(handler, db_factory):
    with db_factory() as db:
        _make_user(db, telegram_chat_id=CHAT_ID, subscription_status="expired")

    asyncio.run(handler._process_webhook_body(_text_update(9, "hello")))
    assert handler.delegated == []
    assert any("sign up" in (text or "").lower() for _, text, _ in handler.sent)


def test_skip_flag_bypasses_gate(monkeypatch, handler, db_factory):
    monkeypatch.setenv("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK", "1")
    asyncio.run(handler._process_webhook_body(_text_update(10, "hello")))
    assert handler.delegated == [10]
    assert handler.sent == []


def test_db_failure_fails_open(monkeypatch, handler):
    def broken_factory():
        raise RuntimeError("db down")

    monkeypatch.setattr(database_module, "SessionLocal", broken_factory)
    asyncio.run(handler._process_webhook_body(_text_update(11, "hello")))
    assert handler.delegated == [11]


def test_non_message_updates_gated_by_chat(handler, db_factory):
    callback = {
        "update_id": 12,
        "callback_query": {
            "id": "cbq",
            "data": "x",
            "message": {
                "message_id": 12,
                "date": 0,
                "chat": {"id": CHAT_ID, "type": "private"},
                "from": {"id": CHAT_ID, "is_bot": False},
                "text": "orig",
            },
        },
    }
    asyncio.run(handler._process_webhook_body(callback))
    assert handler.delegated == []
    assert handler.sent  # link prompt for the unlinked chat
