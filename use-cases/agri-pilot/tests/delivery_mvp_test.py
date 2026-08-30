"""Rider delivery MVP: orders, dispatch, auth."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import marketplace.models  # noqa: F401
from marketplace.auth import hash_password
from marketplace.database import Base, get_db
from marketplace.models import BuyerProfile, ConnectionRequest, FarmerProfile, Listing, RiderProfile, User
from marketplace.routers.auth import router as auth_router
from marketplace.routers.orders_buyer import router as orders_buyer_router
from marketplace.routers.orders_farmer import router as orders_farmer_router
from marketplace.routers.rider import router as rider_router
from marketplace.dispatch_service import accept_job, update_rider_location
from marketplace.order_service import confirm_handoff, create_order, farmer_confirm_order, farmer_mark_ready


def _app_client():
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
    app.include_router(orders_buyer_router)
    app.include_router(orders_farmer_router)
    app.include_router(rider_router)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), TestingSession


def _seed_marketplace(db):
    farmer = User(
        phone_number="+94770002001",
        role="farmer",
        password_hash=hash_password("secret123"),
        name="Farmer",
        subscription_status="active",
    )
    buyer = User(
        phone_number="+94770002002",
        role="buyer",
        password_hash=hash_password("secret123"),
        name="Buyer",
        subscription_status="none",
    )
    rider = User(
        phone_number="+94770002003",
        role="rider",
        password_hash=hash_password("secret123"),
        name="Rider",
        subscription_status="none",
    )
    db.add_all([farmer, buyer, rider])
    db.flush()
    db.add(
        FarmerProfile(
            user_id=farmer.id,
            district="Kandy",
            address_label="Farm gate",
            latitude=7.29,
            longitude=80.63,
        )
    )
    db.add(BuyerProfile(user_id=buyer.id, district="Kandy"))
    db.add(RiderProfile(user_id=rider.id, has_vehicle=True, is_online=False, latitude=7.28, longitude=80.62))
    listing = Listing(farmer_id=farmer.id, crop="tomato", quantity_kg=500, price_per_kg=120, status="active")
    db.add(listing)
    db.flush()
    conn = ConnectionRequest(listing_id=listing.id, buyer_id=buyer.id, status="accepted")
    db.add(conn)
    db.commit()
    return farmer, buyer, rider, listing, conn


def _token(client, phone):
    r = client.post("/api/auth/login", json={"phone_number": phone, "password": "secret123"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_rider_signup_requires_vehicle():
    client, _ = _app_client()
    r = client.post(
        "/api/auth/signup",
        json={
            "role": "rider",
            "phone_number": "+94770002010",
            "password": "secret123",
            "name": "R",
            "has_vehicle": False,
        },
    )
    assert r.status_code == 422


def test_delivery_flow_pickup():
    client, Session = _app_client()
    db = Session()
    farmer, buyer, _, listing, conn = _seed_marketplace(db)
    db.close()

    buyer_tok = _token(client, buyer.phone_number)
    order_resp = client.post(
        "/api/buyer/orders",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={"connection_id": conn.id, "quantity_kg": 100, "fulfillment_mode": "pickup"},
    )
    assert order_resp.status_code == 201, order_resp.text
    order_id = order_resp.json()["order"]["id"]
    pin = order_resp.json()["handoff_pin"]

    farmer_tok = _token(client, farmer.phone_number)
    confirm = client.post(
        f"/api/farmer/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {farmer_tok}"},
        json={"confirmed_quantity_kg": 100, "pickup_latitude": 7.29, "pickup_longitude": 80.63},
    )
    assert confirm.status_code == 200, confirm.text
    ready = client.post(f"/api/farmer/orders/{order_id}/ready", headers={"Authorization": f"Bearer {farmer_tok}"})
    assert ready.status_code == 200, ready.text
    assert ready.json()["status"] == "ready"

    handoff = client.post(
        f"/api/buyer/orders/{order_id}/confirm-handoff",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={"pin": pin},
    )
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["status"] == "delivered"

    db = Session()
    listing_row = db.get(Listing, listing.id)
    assert listing_row.quantity_kg == 400


def test_delivery_flow_with_rider_dispatch():
    client, Session = _app_client()
    db = Session()
    farmer, buyer, rider, _, conn = _seed_marketplace(db)
    db.close()

    buyer_tok = _token(client, buyer.phone_number)
    order_resp = client.post(
        "/api/buyer/orders",
        headers={"Authorization": f"Bearer {buyer_tok}"},
        json={
            "connection_id": conn.id,
            "quantity_kg": 50,
            "fulfillment_mode": "delivery",
            "delivery_address_label": "Shop",
            "delivery_latitude": 7.30,
            "delivery_longitude": 80.64,
        },
    )
    assert order_resp.status_code == 201, order_resp.text
    order_id = order_resp.json()["order"]["id"]
    pin = order_resp.json()["handoff_pin"]

    farmer_tok = _token(client, farmer.phone_number)
    client.post(
        f"/api/farmer/orders/{order_id}/confirm",
        headers={"Authorization": f"Bearer {farmer_tok}"},
        json={"confirmed_quantity_kg": 50, "pickup_latitude": 7.29, "pickup_longitude": 80.63},
    )
    client.post(f"/api/farmer/orders/{order_id}/ready", headers={"Authorization": f"Bearer {farmer_tok}"})

    rider_tok = _token(client, rider.phone_number)
    client.post("/api/rider/online", headers={"Authorization": f"Bearer {rider_tok}"}, json={"online": True})
    client.post(
        "/api/rider/location",
        headers={"Authorization": f"Bearer {rider_tok}"},
        json={"latitude": 7.28, "longitude": 80.62},
    )

    jobs = client.get("/api/rider/jobs", headers={"Authorization": f"Bearer {rider_tok}"})
    assert jobs.status_code == 200, jobs.text
    assert len(jobs.json()) >= 1

    accept = client.post(f"/api/rider/jobs/{order_id}/accept", headers={"Authorization": f"Bearer {rider_tok}"})
    assert accept.status_code == 200, accept.text

    delivery_id = accept.json()["delivery_id"]
    for st in ["en_route_pickup", "arrived_pickup", "picked_up", "in_transit"]:
        r = client.post(
            f"/api/rider/deliveries/{delivery_id}/status",
            headers={"Authorization": f"Bearer {rider_tok}"},
            json={"status": st},
        )
        assert r.status_code == 200, r.text

    complete = client.post(
        f"/api/rider/orders/{order_id}/confirm-handoff",
        headers={"Authorization": f"Bearer {rider_tok}"},
        json={"pin": pin},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "delivered"


def test_concurrent_rider_accept_only_one_wins():
    _, Session = _app_client()
    db = Session()
    farmer, buyer, rider, _, conn = _seed_marketplace(db)
    rider2 = User(
        phone_number="+94770002004",
        role="rider",
        password_hash=hash_password("secret123"),
        name="Rider2",
        subscription_status="none",
    )
    db.add(rider2)
    db.flush()
    db.add(RiderProfile(user_id=rider2.id, has_vehicle=True, is_online=True, latitude=7.281, longitude=80.621))
    order, _pin = create_order(
        db,
        buyer=buyer,
        connection_id=conn.id,
        quantity_kg=20,
        fulfillment_mode="delivery",
        delivery_address_label="X",
        delivery_latitude=7.30,
        delivery_longitude=80.64,
    )
    farmer_confirm_order(
        db,
        farmer=farmer,
        order_id=order.id,
        confirmed_quantity_kg=20,
        pickup_latitude=7.29,
        pickup_longitude=80.63,
    )
    farmer_mark_ready(db, farmer=farmer, order_id=order.id)
    update_rider_location(db, rider, 7.28, 80.62)
    update_rider_location(db, rider2, 7.281, 80.621)
    accept_job(db, rider, order.id)
    with pytest.raises(ValueError, match="not available|already"):
        accept_job(db, rider2, order.id)
    db.close()


def test_handoff_pin_invalid():
    _, Session = _app_client()
    db = Session()
    farmer, buyer, _, _, conn = _seed_marketplace(db)
    order, _ = create_order(
        db,
        buyer=buyer,
        connection_id=conn.id,
        quantity_kg=10,
        fulfillment_mode="pickup",
    )
    farmer_confirm_order(db, farmer=farmer, order_id=order.id, confirmed_quantity_kg=10)
    farmer_mark_ready(db, farmer=farmer, order_id=order.id)
    with pytest.raises(ValueError, match="invalid handoff PIN"):
        confirm_handoff(db, actor=buyer, order_id=order.id, pin="0000")
    db.close()
