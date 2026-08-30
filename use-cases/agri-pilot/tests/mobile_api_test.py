"""Tests for mobile API: JWT chat auth, channels, session identity, public config."""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("OPENAI_API_KEY", "sk-dummy")
os.environ.setdefault("AK_GUARDRAIL__INPUT__ENABLED", "false")
os.environ.setdefault("AK_GUARDRAIL__OUTPUT__ENABLED", "false")
os.environ.setdefault("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK", "1")

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.routers.auth import router as auth_router
from marketplace.routers.config import router as config_router
from marketplace.session_identity import canonical_session_id, is_user_owned_session, parse_canonical_session_id


def test_canonical_session_roundtrip():
    assert parse_canonical_session_id(canonical_session_id(42)) == 42
    assert parse_canonical_session_id("random") is None


def test_user_owned_session_ids():
    assert is_user_owned_session(canonical_session_id(7), 7)
    assert is_user_owned_session("agri:user:7:t:abc", 7)
    assert not is_user_owned_session("agri:user:8:t:abc", 7)
    assert not is_user_owned_session("random", 7)


def _memory_app(extra_routers=None, handlers=None):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    from agentkernel.core.config import AKConfig, _ThreadStoreConfig
    from agentkernel.integration.thread.manager import ConversationThreadManager
    from agentkernel.integration.thread.store.in_memory import InMemoryThreadStore

    AKConfig.get().thread = _ThreadStoreConfig(type="in_memory")
    ConversationThreadManager.reset()
    InMemoryThreadStore._threads.clear()
    InMemoryThreadStore._messages.clear()

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(config_router)
    for r in extra_routers or []:
        app.include_router(r)
    app.dependency_overrides[get_db] = override_get_db

    if handlers:
        from agentkernel.api.http import RESTAPI

        built = RESTAPI.build_app(handlers)
        # mount agent routes from built app
        for route in built.routes:
            app.routes.append(route)

    return TestClient(app), TestingSession


def _signup_farmer(client: TestClient) -> str:
    client.post(
        "/api/auth/signup",
        json={
            "role": "farmer",
            "phone_number": "+94770009901",
            "password": "secret123",
            "name": "Mobile Farmer",
            "district": "Kandy",
        },
    )
    login = client.post(
        "/api/auth/login",
        json={"phone_number": "+94770009901", "password": "secret123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_profile_patch_and_channels():
    client, _ = _memory_app()
    token = _signup_farmer(client)
    headers = {"Authorization": f"Bearer {token}"}
    patch = client.patch("/api/auth/me", headers=headers, json={"name": "Updated", "district": "Galle"})
    assert patch.status_code == 200
    assert patch.json()["name"] == "Updated"
    ch = client.get("/api/auth/me/channels", headers=headers)
    assert ch.status_code == 200
    assert ch.json()["whatsapp"]["linked_by_phone"] is True


def test_public_config():
    client, _ = _memory_app()
    resp = client.get("/api/config/public")
    assert resp.status_code == 200
    body = resp.json()
    assert "telegram_bot_username" in body


def test_chat_requires_jwt():
    import demo  # noqa: F401 — registers agents

    from mobile_api.authenticated_chat_handler import AuthenticatedMobileChatHandler

    client, _ = _memory_app(handlers=[AuthenticatedMobileChatHandler()])
    resp = client.post("/api/v1/chat", json={"prompt": "hello", "session_id": "ignored"})
    assert resp.status_code == 401


def test_authenticated_json_chat_parses_body():
    import demo  # noqa: F401 — registers agents

    from mobile_api.authenticated_chat_handler import AuthenticatedMobileChatHandler

    client, SessionLocal = _memory_app(handlers=[AuthenticatedMobileChatHandler()])
    token = _signup_farmer(client)
    headers = {"Authorization": f"Bearer {token}"}
    with SessionLocal() as db:
        from marketplace.models import User

        user = db.query(User).filter(User.phone_number == "+94770009901").one()
        session_id = canonical_session_id(user.id)

    resp = client.post(
        "/api/v1/chat",
        headers=headers,
        json={"prompt": "What treatment do you recommend?", "session_id": session_id, "agent": "triage"},
    )
    assert resp.status_code != 422, resp.text
    detail = resp.json().get("detail")
    if isinstance(detail, list):
        assert not any(item.get("type") == "missing" for item in detail if isinstance(item, dict))


def test_telegram_link_token_and_unlink():
    client, SessionLocal = _memory_app()
    token = _signup_farmer(client)
    headers = {"Authorization": f"Bearer {token}"}
    link = client.post("/api/auth/me/channels/telegram/link-token", headers=headers)
    assert link.status_code == 200
    assert "deep_link_url" in link.json()
    unlink = client.delete("/api/auth/me/channels/telegram", headers=headers)
    assert unlink.status_code == 204
