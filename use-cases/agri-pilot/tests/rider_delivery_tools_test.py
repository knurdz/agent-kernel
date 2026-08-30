"""Tests for rider read-only delivery chat tools."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.auth import hash_password
from marketplace.database import Base
from marketplace.dispatch_service import accept_job, update_rider_location
from marketplace.models import (
    BuyerProfile,
    ConnectionRequest,
    FarmerProfile,
    Listing,
    RiderProfile,
    User,
)
from marketplace.order_service import create_order, farmer_confirm_order, farmer_mark_ready
from tools.delivery_tools import my_orders_tool, nearby_delivery_jobs_tool


def _memory_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _seed_delivery(db):
    farmer = User(
        phone_number="+94770003001",
        role="farmer",
        password_hash=hash_password("secret123"),
        name="Farmer",
        subscription_status="active",
    )
    buyer = User(
        phone_number="+94770003002",
        role="buyer",
        password_hash=hash_password("secret123"),
        name="Buyer",
        subscription_status="none",
    )
    rider = User(
        phone_number="+94770003003",
        role="rider",
        password_hash=hash_password("secret123"),
        name="Rider",
        subscription_status="none",
    )
    db.add_all([farmer, buyer, rider])
    db.flush()
    db.add(FarmerProfile(user_id=farmer.id, district="Kandy", latitude=7.29, longitude=80.63))
    db.add(BuyerProfile(user_id=buyer.id, district="Colombo"))
    db.add(RiderProfile(user_id=rider.id, has_vehicle=True, is_online=False, latitude=7.28, longitude=80.62))
    listing = Listing(
        farmer_id=farmer.id,
        crop="tomato",
        quantity_kg=100,
        price_per_kg=120,
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(listing)
    db.flush()
    conn = ConnectionRequest(
        listing_id=listing.id,
        buyer_id=buyer.id,
        status="accepted",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(conn)
    db.commit()
    return farmer, buyer, rider, conn


@patch("tools.delivery_tools._get_session_identity")
def test_nearby_jobs_offline_hint(mock_identity):
    db = _memory_db()
    _, _, rider, _ = _seed_delivery(db)
    mock_identity.return_value = (rider.id, "rider", None)

    with patch("marketplace.database.SessionLocal", return_value=db):
        result = nearby_delivery_jobs_tool(limit=5)

    assert result["ok"] is True
    assert result["jobs"] == []
    assert result["hint"] == "offline"
    assert "Online" in result["message"]


@patch("tools.delivery_tools._get_session_identity")
def test_my_orders_rider_includes_crop(mock_identity):
    db = _memory_db()
    farmer, buyer, rider, conn = _seed_delivery(db)
    order = create_order(
        db,
        buyer=buyer,
        connection_id=conn.id,
        quantity_kg=50,
        fulfillment_mode="delivery",
        delivery_address_label="Colombo shop",
        delivery_latitude=6.93,
        delivery_longitude=79.85,
    )
    farmer_confirm_order(
        db,
        farmer=farmer,
        order_id=order.id,
        confirmed_quantity_kg=50,
        pickup_address_label="Farm gate",
        pickup_latitude=7.29,
        pickup_longitude=80.63,
    )
    farmer_mark_ready(db, farmer=farmer, order_id=order.id)
    update_rider_location(db, rider, 7.28, 80.62)
    rp = db.get(RiderProfile, rider.id)
    rp.is_online = True
    db.commit()
    accept_job(db, rider, order.id)

    mock_identity.return_value = (rider.id, "rider", None)

    with patch("marketplace.database.SessionLocal", return_value=db):
        result = my_orders_tool(limit=5)

    assert result["ok"] is True
    assert result["role"] == "rider"
    assert len(result["deliveries"]) >= 1
    first = result["deliveries"][0]
    assert first["crop"] == "tomato"
    assert first["quantity_kg"] == 50
    assert first.get("pickup_label") == "Farm gate"
    assert first.get("delivery_label") == "Colombo shop"
