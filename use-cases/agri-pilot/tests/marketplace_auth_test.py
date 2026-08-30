"""Phase 15.2: auth signup/login/me."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.routers.auth import router as auth_router


def _client_with_memory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    return client, engine, TestingSession


def test_signup_farmer_and_buyer():
    client, _, _ = _client_with_memory()
    r = client.post(
        "/api/auth/signup",
        json={
            "role": "farmer",
            "phone_number": "+94770001001",
            "password": "secret123",
            "name": "Amal",
            "district": "Kandy",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "farmer"
    r2 = client.post(
        "/api/auth/signup",
        json={
            "role": "buyer",
            "phone_number": "+94770001002",
            "password": "secret123",
            "name": "Buyer",
            "district": "Galle",
        },
    )
    assert r2.status_code == 201, r2.text


def test_duplicate_phone_409():
    client, _, _ = _client_with_memory()
    payload = {"role": "farmer", "phone_number": "+94770001003", "password": "secret123", "name": "A"}
    assert client.post("/api/auth/signup", json=payload).status_code == 201
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 409
    assert "phone already registered" in r.json()["detail"]


def test_invalid_phone_422():
    client, _, _ = _client_with_memory()
    r = client.post(
        "/api/auth/signup",
        json={"role": "farmer", "phone_number": "077000", "password": "secret123", "name": "A"},
    )
    assert r.status_code == 422


def test_short_password_422():
    client, _, _ = _client_with_memory()
    r = client.post(
        "/api/auth/signup",
        json={"role": "farmer", "phone_number": "+94770001004", "password": "short", "name": "A"},
    )
    assert r.status_code == 422


def test_admin_rejected():
    client, _, _ = _client_with_memory()
    # Pydantic will reject role literal, expect 422
    r = client.post(
        "/api/auth/signup",
        json={"role": "admin", "phone_number": "+94770001005", "password": "secret123", "name": "A"},
    )
    assert r.status_code == 422


def test_login_and_me():
    client, _, _ = _client_with_memory()
    client.post(
        "/api/auth/signup",
        json={"role": "farmer", "phone_number": "+94770001006", "password": "secret123", "name": "Amal"},
    )
    r = client.post("/api/auth/login", json={"phone_number": "+94770001006", "password": "secret123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    # wrong password
    r2 = client.post("/api/auth/login", json={"phone_number": "+94770001006", "password": "wrongpass"})
    assert r2.status_code == 401
    assert r2.json()["detail"] == "invalid credentials"

    # unknown phone
    r3 = client.post("/api/auth/login", json={"phone_number": "+94770001999", "password": "secret123"})
    assert r3.status_code == 401
    assert r3.json()["detail"] == "invalid credentials"

    # me
    r4 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r4.status_code == 200, r4.text
    assert r4.json()["phone_number"] == "+94770001006"
    assert "password_hash" not in r4.text

    # me without token
    assert client.get("/api/auth/me").status_code == 401

    # me with invalid token
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer invalid"}).status_code == 401


def test_phone_normalization_strips_spaces_dashes():
    client, _, _ = _client_with_memory()
    # signup with spaced/dashed phone should normalize to +94770001007
    r = client.post(
        "/api/auth/signup",
        json={"role": "farmer", "phone_number": "+94 770-000 1007", "password": "secret123", "name": "Norm"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["phone_number"] == "+947700001007"
    # login with differently formatted phone should also work
    r2 = client.post("/api/auth/login", json={"phone_number": "+94-770-000-1007", "password": "secret123"})
    assert r2.status_code == 200


def test_hash_verify_roundtrip():
    from marketplace.auth import hash_password, verify_password

    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_signup_local_sl_phone_formats():
    client, _, _ = _client_with_memory()
    r = client.post(
        "/api/auth/signup",
        json={
            "role": "farmer",
            "phone_number": "0770001008",
            "password": "secret123",
            "name": "Local",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["phone_number"] == "+94770001008"


def test_login_sl_phone_without_plus():
    client, _, _ = _client_with_memory()
    client.post(
        "/api/auth/signup",
        json={
            "role": "farmer",
            "phone_number": "+94770001009",
            "password": "secret123",
            "name": "LoginFmt",
        },
    )
    r = client.post(
        "/api/auth/login",
        json={"phone_number": "94770001009", "password": "secret123"},
    )
    assert r.status_code == 200, r.text


def test_normalize_phone_unit():
    from marketplace.auth import normalize_phone

    assert normalize_phone("0741174199") == "+94741174199"
    assert normalize_phone("741174199") == "+94741174199"
    assert normalize_phone("94741175199") == "+94741175199"
    assert normalize_phone("+94 741-174 199") == "+94741174199"

    with pytest.raises(ValueError):
        normalize_phone("74115199")
