"""Phase 15.3: farmer listings CRUD + subscription gating."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.models import User
from marketplace.routers.auth import router as auth_router
from marketplace.routers.farmer import router as farmer_router


def _app_with_memory():
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
    app.include_router(farmer_router)
    app.dependency_overrides[get_db] = override_get_db
    return app, engine, TestingSession


def _signup_login(client, phone, role="farmer"):
    client.post(
        "/api/auth/signup",
        json={"role": role, "phone_number": phone, "password": "secret123", "name": "User", "district": "Kandy"},
    )
    r = client.post("/api/auth/login", json={"phone_number": phone, "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_farmer_crud_own_only():
    app, engine, Session = _app_with_memory()
    client = TestClient(app)
    t1 = _signup_login(client, "+94770002001", "farmer")
    t2 = _signup_login(client, "+94770002002", "farmer")
    h1 = {"Authorization": f"Bearer {t1}"}
    h2 = {"Authorization": f"Bearer {t2}"}

    # create
    r = client.post(
        "/api/farmer/listings", headers=h1, json={"crop": "Tomato", "quantity_kg": 500, "price_per_kg": 120}
    )
    assert r.status_code == 201, r.text
    lid = r.json()["id"]
    assert r.json()["crop"] == "tomato"

    # list own only
    r1 = client.get("/api/farmer/listings", headers=h1)
    assert r1.status_code == 200
    assert r1.json()["total"] == 1
    r2 = client.get("/api/farmer/listings", headers=h2)
    assert r2.json()["total"] == 0

    # non-owner patch 404
    assert client.patch(f"/api/farmer/listings/{lid}", headers=h2, json={"quantity_kg": 600}).status_code == 404

    # valid patch
    r3 = client.patch(f"/api/farmer/listings/{lid}", headers=h1, json={"quantity_kg": 600})
    assert r3.status_code == 200
    assert r3.json()["quantity_kg"] == 600

    # invalid quantity
    assert client.patch(f"/api/farmer/listings/{lid}", headers=h1, json={"quantity_kg": 0}).status_code == 422

    # status transition sold -> active blocked
    assert client.patch(f"/api/farmer/listings/{lid}", headers=h1, json={"status": "sold"}).status_code == 200
    r4 = client.patch(f"/api/farmer/listings/{lid}", headers=h1, json={"status": "active"})
    assert r4.status_code == 400

    # delete
    assert client.delete(f"/api/farmer/listings/{lid}", headers=h1).status_code == 204
    assert client.patch(f"/api/farmer/listings/{lid}", headers=h1, json={"quantity_kg": 700}).status_code == 404
    assert client.delete(f"/api/farmer/listings/{lid}", headers=h1).status_code == 404


def test_buyer_blocked():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    tb = _signup_login(client, "+94770002003", "buyer")
    hb = {"Authorization": f"Bearer {tb}"}
    assert client.post("/api/farmer/listings", headers=hb, json={"crop": "rice", "quantity_kg": 10}).status_code == 403


def test_pagination_and_filter():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    tok = _signup_login(client, "+94770002004", "farmer")
    h = {"Authorization": f"Bearer {tok}"}
    for qty in [100, 200, 300]:
        client.post("/api/farmer/listings", headers=h, json={"crop": "rice", "quantity_kg": qty})
    r = client.get("/api/farmer/listings?limit=1&offset=1", headers=h)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1
    r2 = client.get("/api/farmer/listings?status=active", headers=h)
    assert r2.json()["total"] == 3


def test_subscription_gate_and_bypass():
    app, engine, Session = _app_with_memory()
    client = TestClient(app)
    tok = _signup_login(client, "+94770002005", "farmer")
    h = {"Authorization": f"Bearer {tok}"}
    # works initially (active)
    assert client.post("/api/farmer/listings", headers=h, json={"crop": "tea", "quantity_kg": 50}).status_code == 201

    # set expired
    db = Session()
    u = db.scalars(select(User).where(User.phone_number == "+94770002005")).first()
    u.subscription_status = "expired"
    db.commit()
    db.close()
    r = client.post("/api/farmer/listings", headers=h, json={"crop": "tea", "quantity_kg": 50})
    assert r.status_code == 403
    assert "expired" in r.json()["detail"]
    assert client.get("/api/farmer/listings", headers=h).status_code == 403

    # bypass env
    os.environ["AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK"] = "1"
    try:
        assert (
            client.post("/api/farmer/listings", headers=h, json={"crop": "tea", "quantity_kg": 50}).status_code == 201
        )
    finally:
        os.environ.pop("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK", None)


def test_create_listing_service_shared():
    """REST handler and service share logic; crop normalization etc."""
    # Patch marketplace.service.create_listing and ensure router calls it
    from unittest.mock import patch

    app, _, _ = _app_with_memory()
    client = TestClient(app)
    tok = _signup_login(client, "+94770002006", "farmer")
    h = {"Authorization": f"Bearer {tok}"}
    with patch(
        "marketplace.routers.farmer.create_listing",
        wraps=__import__("marketplace.service", fromlist=["create_listing"]).create_listing,
    ) as m:
        client.post("/api/farmer/listings", headers=h, json={"crop": "Maize", "quantity_kg": 100})
        assert m.called
