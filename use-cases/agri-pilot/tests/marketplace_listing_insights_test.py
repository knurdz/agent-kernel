"""Tests for listing insights schema and buyer listing insights API."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base, get_db
from marketplace.models import Listing, Plant, PlantObservation, User
from marketplace.routers.auth import router as auth_router
from marketplace.routers.buyer import router as buyer_router


def _app():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(buyer_router)
    app.dependency_overrides[get_db] = override_get_db
    return app, Session


def _signup_login(client, phone, role="buyer"):
    client.post(
        "/api/auth/signup",
        json={"role": role, "phone_number": phone, "password": "secret123", "name": "User", "district": "Kandy"},
    )
    r = client.post("/api/auth/login", json={"phone_number": phone, "password": "secret123"})
    return r.json()["access_token"]


def test_listing_insights_includes_health_series():
    app, Session = _app()
    client = TestClient(app)
    _signup_login(client, "+94770002001", "farmer")
    buyer_token = _signup_login(client, "+94770002002", "buyer")

    db = Session()
    try:
        farmer = db.scalars(select(User).where(User.phone_number == "+94770002001")).first()
        listing = Listing(
            farmer_id=farmer.id,
            crop="tomato",
            quantity_kg=300,
            price_per_kg=100,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(listing)
        db.flush()
        plant = Plant(
            farmer_id=farmer.id,
            crop="tomato",
            name="Tomatoes",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(plant)
        db.flush()
        listing.plant_id = plant.id
        plant.listing_id = listing.id
        db.add(
            PlantObservation(
                plant_id=plant.id,
                photo_path="a.jpg",
                captured_at=datetime.now(timezone.utc),
                quality_ok=True,
                top_label="Tomato___healthy",
                top_confidence=0.9,
                source="test",
            )
        )
        db.commit()
        listing_id = listing.id
    finally:
        db.close()

    resp = client.get(
        f"/api/buyer/listings/{listing_id}/insights",
        headers={"Authorization": f"Bearer {buyer_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["observation_count"] == 1
    assert data["health_series"]
    assert data["trend"] in {"unknown", "stable", "improving", "worsening"}
