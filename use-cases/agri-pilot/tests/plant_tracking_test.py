"""Plant tracking, one-time scans, and buyer listing insights."""

import io
import os
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.models import Listing, Plant, PlantObservation, User
from marketplace.routers.auth import router as auth_router
from marketplace.routers.buyer import router as buyer_router
from marketplace.routers.farmer import router as farmer_router
from marketplace.routers.plants import router as plants_router


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
    app.include_router(plants_router)
    app.include_router(buyer_router)
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


def _create_listing(client, token, crop="tomato"):
    r = client.post(
        "/api/farmer/listings",
        headers={"Authorization": f"Bearer {token}"},
        json={"crop": crop, "quantity_kg": 100, "price_per_kg": 120},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


MOCK_ANALYSIS = {
    "quality_ok": True,
    "quality_reason": None,
    "metrics": {},
    "predictions": [{"label": "Tomato___Early_blight", "confidence": 0.91}],
    "top_label": "Tomato___Early_blight",
    "top_confidence": 0.91,
    "confident": True,
    "advice_summary": "Remove affected leaves promptly.",
}


def test_one_time_scan_does_not_create_plant(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIPILOT_PLANT_MEDIA_ROOT", str(tmp_path))
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    token = _signup_login(client, "+94770003001")

    with patch("marketplace.routers.plants.analyze_crop_photo", return_value=MOCK_ANALYSIS):
        r = client.post(
            "/api/farmer/scans",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("leaf.jpg", b"fake-image-bytes", "image/jpeg")},
            data={"crop": "tomato"},
        )
    assert r.status_code == 200, r.text
    assert r.json()["confident"] is True
    assert r.json()["top_label"] == "Tomato___Early_blight"

    plants = client.get("/api/farmer/plants", headers={"Authorization": f"Bearer {token}"})
    assert plants.json()["total"] == 0


def test_plant_crud_and_observation(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIPILOT_PLANT_MEDIA_ROOT", str(tmp_path))
    app, _, Session = _app_with_memory()
    client = TestClient(app)
    token = _signup_login(client, "+94770003002")

    r = client.post(
        "/api/farmer/plants",
        headers={"Authorization": f"Bearer {token}"},
        json={"crop": "tomato", "name": "Field A"},
    )
    assert r.status_code == 201, r.text
    plant_id = r.json()["id"]

    with patch("marketplace.routers.plants.analyze_crop_photo", return_value=MOCK_ANALYSIS):
        obs = client.post(
            f"/api/farmer/plants/{plant_id}/observations",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("leaf.jpg", b"fake-image-bytes", "image/jpeg")},
        )
    assert obs.status_code == 201, obs.text
    assert obs.json()["top_label"] == "Tomato___Early_blight"
    assert "photo_url" in obs.json()

    detail = client.get(f"/api/farmer/plants/{plant_id}", headers={"Authorization": f"Bearer {token}"})
    assert detail.status_code == 200
    assert detail.json()["insights"]["observation_count"] == 1


def test_import_from_listing_unique_link(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIPILOT_PLANT_MEDIA_ROOT", str(tmp_path))
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    token = _signup_login(client, "+94770003003")
    listing_id = _create_listing(client, token)

    r1 = client.post(
        f"/api/farmer/listings/{listing_id}/import-plant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["listing_id"] == listing_id

    r2 = client.post(
        f"/api/farmer/listings/{listing_id}/import-plant",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 409

    listings = client.get("/api/farmer/listings", headers={"Authorization": f"Bearer {token}"})
    assert listings.json()["items"][0]["plant_id"] == r1.json()["id"]


def test_buyer_insights_public_no_photos(tmp_path, monkeypatch):
    monkeypatch.setenv("AGRIPILOT_PLANT_MEDIA_ROOT", str(tmp_path))
    app, _, Session = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003004")
    buyer_token = _signup_login(client, "+94770003005", role="buyer")
    listing_id = _create_listing(client, farmer_token)

    import_resp = client.post(
        f"/api/farmer/listings/{listing_id}/import-plant",
        headers={"Authorization": f"Bearer {farmer_token}"},
    )
    plant_id = import_resp.json()["id"]

    with patch("marketplace.routers.plants.analyze_crop_photo", return_value=MOCK_ANALYSIS):
        client.post(
            f"/api/farmer/plants/{plant_id}/observations",
            headers={"Authorization": f"Bearer {farmer_token}"},
            files={"image": ("leaf.jpg", b"fake-image-bytes", "image/jpeg")},
        )

    insights = client.get(
        f"/api/buyer/listings/{listing_id}/insights",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert insights.status_code == 200, insights.text
    body = insights.json()
    assert body["observation_count"] == 1
    assert body["latest_label"] == "Tomato___Early_blight"
    assert "photo" not in str(body).lower() or "photo_url" not in body


def test_buyer_insights_404_when_unlinked():
    app, _, _ = _app_with_memory()
    client = TestClient(app)
    farmer_token = _signup_login(client, "+94770003006")
    buyer_token = _signup_login(client, "+94770003007", role="buyer")
    listing_id = _create_listing(client, farmer_token)

    r = client.get(
        f"/api/buyer/listings/{listing_id}/insights",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert r.status_code == 404


def test_analyze_crop_photo_quality_fail(tmp_path):
    from PIL import Image
    import numpy as np

    from tools.vision_tool import analyze_crop_photo

    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    path = tmp_path / "dark.png"
    Image.fromarray(arr, mode="RGB").save(path)

    result = analyze_crop_photo(str(path), crop="tomato")
    assert result["quality_ok"] is False
    assert result["predictions"] == []


def test_analyze_crop_photo_confident(monkeypatch, tmp_path):
    from tools.vision_tool import analyze_crop_photo

    monkeypatch.setattr(
        "tools.vision_tool.check_image_quality",
        lambda _p: {"ok": True, "reason": None, "metrics": {}},
    )
    monkeypatch.setattr(
        "tools.vision_tool.diagnose_crop_image",
        lambda _p: {"predictions": [{"label": "Tomato___Early_blight", "confidence": 0.92}]},
    )
    monkeypatch.setattr(
        "tools.vision_tool._short_advice_from_rag",
        lambda _c, _d: "Remove affected leaves.",
    )

    result = analyze_crop_photo(str(tmp_path / "x.jpg"), crop="tomato")
    assert result["quality_ok"] is True
    assert result["confident"] is True
    assert result["top_label"] == "Tomato___Early_blight"


def test_analyze_crop_photo_low_confidence(monkeypatch, tmp_path):
    from tools.vision_tool import analyze_crop_photo

    monkeypatch.setattr(
        "tools.vision_tool.check_image_quality",
        lambda _p: {"ok": True, "reason": None, "metrics": {}},
    )
    monkeypatch.setattr(
        "tools.vision_tool.diagnose_crop_image",
        lambda _p: {"predictions": [{"label": "Tomato___Early_blight", "confidence": 0.4}]},
    )

    result = analyze_crop_photo(str(tmp_path / "x.jpg"), crop="tomato")
    assert result["quality_ok"] is True
    assert result["confident"] is False
