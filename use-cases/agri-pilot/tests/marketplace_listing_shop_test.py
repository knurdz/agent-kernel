"""Listing shop: photos, buyer browse, analytics."""

import io
import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.routers.auth import router as auth_router
from marketplace.routers.buyer import router as buyer_router
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
    app.include_router(buyer_router)
    app.dependency_overrides[get_db] = override_get_db
    return app, engine, TestingSession


def _signup_login(client, phone, role="farmer", district="Kandy"):
    client.post(
        "/api/auth/signup",
        json={"role": role, "phone_number": phone, "password": "secret123", "name": "User", "district": district},
    )
    r = client.post("/api/auth/login", json={"phone_number": phone, "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _create_listing(client, farmer_token, **kwargs):
    payload = {"crop": "tomato", "quantity_kg": 500, "price_per_kg": 120, "category": "vegetable", **kwargs}
    r = client.post("/api/farmer/listings", headers={"Authorization": f"Bearer {farmer_token}"}, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def listing_media_tmp(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("AGRIPILOT_LISTING_MEDIA_ROOT", tmp)
        yield tmp


def test_listing_create_with_category_and_description():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    token = _signup_login(client, "+94770003001", "farmer")
    h = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/api/farmer/listings",
        headers=h,
        json={
            "crop": "Chili",
            "quantity_kg": 100,
            "category": "spice",
            "description": "Fresh red chili",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["crop"] == "chili"
    assert body["category"] == "spice"
    assert body["description"] == "Fresh red chili"
    assert body["available_kg"] == 100
    assert body["view_count"] == 0


def test_listing_photo_upload_and_get(listing_media_tmp):
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    token = _signup_login(client, "+94770003002", "farmer")
    h = {"Authorization": f"Bearer {token}"}
    listing = _create_listing(client, token)
    lid = listing["id"]

    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
        b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    r = client.post(
        f"/api/farmer/listings/{lid}/photo",
        headers=h,
        files={"image": ("crop.png", io.BytesIO(png_bytes), "image/png")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["photo_url"] == f"/api/farmer/listings/{lid}/photo"

    photo = client.get(f"/api/farmer/listings/{lid}/photo", headers=h)
    assert photo.status_code == 200
    assert photo.content == png_bytes


def test_listing_analytics_and_detail():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003003", "farmer")
    buyer_token = _signup_login(client, "+94770003004", "buyer")
    fh = {"Authorization": f"Bearer {farmer_token}"}
    bh = {"Authorization": f"Bearer {buyer_token}"}
    listing = _create_listing(client, farmer_token)
    lid = listing["id"]

    detail = client.get(f"/api/farmer/listings/{lid}", headers=fh)
    assert detail.status_code == 200
    assert detail.json()["reserved_quantity_kg"] == 0

    analytics = client.get(f"/api/farmer/listings/{lid}/analytics", headers=fh)
    assert analytics.status_code == 200
    assert analytics.json()["view_count"] == 0
    assert analytics.json()["available_kg"] == 500

    client.post(f"/api/buyer/listings/{lid}/connect", headers=bh, json={"message": "hi"})
    analytics2 = client.get(f"/api/farmer/listings/{lid}/analytics", headers=fh)
    assert analytics2.json()["connections_pending"] == 1


def test_buyer_browse_empty_filters_returns_all_active():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003005", "farmer")
    buyer_token = _signup_login(client, "+94770003006", "buyer")
    bh = {"Authorization": f"Bearer {buyer_token}"}

    _create_listing(client, farmer_token, crop="tomato")
    _create_listing(client, farmer_token, crop="potato", category="vegetable")

    r = client.get("/api/buyer/listings", headers=bh)
    assert r.status_code == 200
    assert r.json()["total"] == 2
    assert len(r.json()["items"]) == 2
    for item in r.json()["items"]:
        assert "farmer_name" in item
        assert "district" in item
        assert "available_kg" in item
        assert item["reserved_quantity_kg"] is None


def test_buyer_browse_crop_substring_and_category():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003007", "farmer")
    buyer_token = _signup_login(client, "+94770003008", "buyer")
    bh = {"Authorization": f"Bearer {buyer_token}"}

    _create_listing(client, farmer_token, crop="tomato")
    _create_listing(client, farmer_token, crop="potato")
    _create_listing(client, farmer_token, crop="mango", category="fruit")

    r = client.get("/api/buyer/listings?crop=tom", headers=bh)
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["crop"] == "tomato"

    r2 = client.get("/api/buyer/listings?category=fruit", headers=bh)
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["crop"] == "mango"


def test_buyer_listing_detail_increments_view_count():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003009", "farmer")
    buyer_token = _signup_login(client, "+94770003010", "buyer")
    fh = {"Authorization": f"Bearer {farmer_token}"}
    bh = {"Authorization": f"Bearer {buyer_token}"}
    listing = _create_listing(client, farmer_token)
    lid = listing["id"]

    r1 = client.get(f"/api/buyer/listings/{lid}", headers=bh)
    assert r1.status_code == 200
    assert r1.json()["view_count"] == 1

    r2 = client.get(f"/api/buyer/listings/{lid}", headers=bh)
    assert r2.json()["view_count"] == 2

    analytics = client.get(f"/api/farmer/listings/{lid}/analytics", headers=fh)
    assert analytics.json()["view_count"] == 2


def test_quantity_cannot_go_below_reserved():
    app, _, Session = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003011", "farmer")
    h = {"Authorization": f"Bearer {farmer_token}"}
    listing = _create_listing(client, farmer_token, quantity_kg=500)
    lid = listing["id"]

    db = Session()
    from marketplace.models import Listing

    row = db.get(Listing, lid)
    row.reserved_quantity_kg = 200
    db.commit()
    db.close()

    r = client.patch(f"/api/farmer/listings/{lid}", headers=h, json={"quantity_kg": 100})
    assert r.status_code == 400
    assert "reserved" in r.json()["detail"].lower()

    r2 = client.patch(f"/api/farmer/listings/{lid}", headers=h, json={"quantity_kg": 250})
    assert r2.status_code == 200
