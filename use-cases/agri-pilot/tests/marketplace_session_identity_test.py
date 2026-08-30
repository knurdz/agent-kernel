"""Session identity parsing and marketplace tool auth for mobile advisor threads."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from agentkernel.core.base import Session
from agentkernel.core.tool import ToolContext
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK", "1")

import marketplace.models  # noqa: F401
from marketplace.database import Base
from marketplace.models import User
from marketplace.session_identity import parse_canonical_session_id
from tools.marketplace_tools import _get_session_identity, browse_listings_tool


def test_parse_canonical_session_id_mobile_thread():
    assert parse_canonical_session_id("agri:user:7:t:1730000000-12345") == 7
    assert parse_canonical_session_id("agri:user:42") == 42
    assert parse_canonical_session_id("agri:user:x") is None
    assert parse_canonical_session_id("random") is None
    assert parse_canonical_session_id(None) is None


@pytest.fixture
def buyer_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("marketplace.database.SessionLocal", TestingSession)

    with TestingSession() as db:
        buyer = User(
            role="buyer",
            phone_number="+94770008801",
            password_hash="x",
            name="Buyer",
            subscription_status="active",
        )
        db.add(buyer)
        db.commit()
        db.refresh(buyer)
        yield buyer, TestingSession


def _tool_context_for_session(session: Session) -> ToolContext:
    ctx = ToolContext(MagicMock(), MagicMock(), session, [])
    ctx.set()
    return ctx


def test_get_session_identity_from_mobile_thread_id(buyer_db):
    buyer, _ = buyer_db
    session = Session(id=f"agri:user:{buyer.id}:t:1730000000-999")
    ctx = _tool_context_for_session(session)
    try:
        uid, role, sub = _get_session_identity()
        assert uid == buyer.id
        assert role == "buyer"
        assert sub == "active"
        assert session.get("marketplace_user_id") == buyer.id
    finally:
        ctx.reset()


def test_browse_listings_tool_authenticated_via_mobile_thread_id(buyer_db):
    buyer, _ = buyer_db
    session = Session(id=f"agri:user:{buyer.id}:t:1730000000-999")
    ctx = _tool_context_for_session(session)
    try:
        result = browse_listings_tool(crop="tomato", limit=5)
        assert result.get("error") != "not authenticated"
        assert "items" in result
    finally:
        ctx.reset()
