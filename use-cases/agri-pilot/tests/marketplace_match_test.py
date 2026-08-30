"""Tests for enriched buyer match scoring."""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.database import Base
from marketplace.models import BuyerProfile, ConnectionRequest, FarmerProfile, Listing, Plant, PlantObservation, User
from marketplace.service import create_user_with_profile, match_listings


def _memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _farmer_listing(db, *, farmer_id, crop="tomato", qty=500, price=120, plant_id=None, harvest_date=None, district="Kandy"):
    lst = Listing(
        farmer_id=farmer_id,
        crop=crop,
        quantity_kg=qty,
        price_per_kg=price,
        harvest_date=harvest_date,
        plant_id=plant_id,
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(lst)
    db.flush()
    fp = db.get(FarmerProfile, farmer_id)
    if fp:
        fp.district = district
    return lst


def test_match_prefers_exact_district_and_healthier_tracked_listing():
    db = _memory_db()
    buyer = create_user_with_profile(
        db,
        role="buyer",
        phone_number="+94770001001",
        password_hash="x",
        name="Buyer",
        district="Kandy",
    )
    f1 = create_user_with_profile(
        db,
        role="farmer",
        phone_number="+94770001002",
        password_hash="x",
        name="Farmer A",
        district="Kandy",
    )
    f2 = create_user_with_profile(
        db,
        role="farmer",
        phone_number="+94770001003",
        password_hash="x",
        name="Farmer B",
        district="Colombo",
    )
    db.commit()

    plant = Plant(farmer_id=f1.id, crop="tomato", name="Tomatoes", created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    db.add(plant)
    db.flush()
    db.add(
        PlantObservation(
            plant_id=plant.id,
            photo_path="x.jpg",
            captured_at=datetime.now(timezone.utc),
            quality_ok=True,
            top_label="Tomato___healthy",
            top_confidence=0.95,
            source="test",
        )
    )
    db.add(
        PlantObservation(
            plant_id=plant.id,
            photo_path="y.jpg",
            captured_at=datetime.now(timezone.utc),
            quality_ok=True,
            top_label="Tomato___healthy",
            top_confidence=0.92,
            source="test",
        )
    )
    db.flush()

    lst_tracked = _farmer_listing(db, farmer_id=f1.id, price=130, plant_id=plant.id, district="Kandy")
    plant.listing_id = lst_tracked.id
    _farmer_listing(db, farmer_id=f2.id, price=100, district="Colombo")
    db.commit()

    results = match_listings(db, crop="tomato", district="Kandy", quantity_kg=200, limit=10)
    assert len(results) == 2
    assert results[0]["listing"].id == lst_tracked.id
    assert results[0]["health"]["tracked"] is True
    assert results[0]["district"] == "Kandy"
    assert results[0]["score"] > results[1]["score"]


def test_match_includes_health_summary_for_untracked():
    db = _memory_db()
    create_user_with_profile(db, role="buyer", phone_number="+94770001011", password_hash="x", name="Buyer")
    farmer = create_user_with_profile(
        db, role="farmer", phone_number="+94770001012", password_hash="x", name="Farmer", district="Kandy"
    )
    db.commit()
    _farmer_listing(db, farmer_id=farmer.id)
    db.commit()

    results = match_listings(db, crop="tomato", district="Kandy")
    assert len(results) == 1
    assert results[0]["health"]["tracked"] is False
