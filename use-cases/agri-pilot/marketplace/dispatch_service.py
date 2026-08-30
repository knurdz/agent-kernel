"""Rider dispatch service — job search, accept/reject, location, status."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from marketplace.delivery_utils import (
    bounding_box,
    get_dispatch_radius_km,
    get_location_stale_seconds,
    get_min_location_interval_seconds,
    haversine_km,
    valid_coordinate,
)
from marketplace.maps_service import estimate_route
from marketplace.models import (
    Delivery,
    DeliveryStatus,
    Order,
    OrderStatus,
    RiderJobDecision,
    RiderJobDecisionType,
    RiderProfile,
    User,
    UserRole,
)
from marketplace.order_service import _record_event, _transition_order

# Rider delivery status transitions
_DELIVERY_TRANSITIONS: dict[str, set[str]] = {
    DeliveryStatus.assigned.value: {DeliveryStatus.en_route_pickup.value},
    DeliveryStatus.en_route_pickup.value: {DeliveryStatus.arrived_pickup.value},
    DeliveryStatus.arrived_pickup.value: {DeliveryStatus.picked_up.value},
    DeliveryStatus.picked_up.value: {DeliveryStatus.in_transit.value},
    DeliveryStatus.in_transit.value: {DeliveryStatus.delivered.value},
}

_ORDER_FOR_DELIVERY: dict[str, str] = {
    DeliveryStatus.en_route_pickup.value: OrderStatus.en_route_pickup.value,
    DeliveryStatus.arrived_pickup.value: OrderStatus.arrived_pickup.value,
    DeliveryStatus.picked_up.value: OrderStatus.picked_up.value,
    DeliveryStatus.in_transit.value: OrderStatus.in_transit.value,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_or_create_rider_profile(db: Session, rider: User) -> RiderProfile:
    if rider.role != UserRole.rider.value:
        raise ValueError("rider role required")
    if rider.rider_profile is None:
        rp = RiderProfile(user_id=rider.id, has_vehicle=False, is_online=False)
        db.add(rp)
        db.flush()
        return rp
    return rider.rider_profile


def set_rider_online(db: Session, rider: User, online: bool) -> RiderProfile:
    rp = _get_or_create_rider_profile(db, rider)
    if online and not rp.has_vehicle:
        raise ValueError("vehicle confirmation required before going online")
    rp.is_online = online
    rp.updated_at = _utcnow()
    db.commit()
    db.refresh(rp)
    return rp


def update_rider_location(
    db: Session,
    rider: User,
    latitude: float,
    longitude: float,
    heading: Optional[float] = None,
    accuracy_m: Optional[float] = None,
) -> RiderProfile:
    if not valid_coordinate(latitude, longitude):
        raise ValueError("invalid coordinates")
    rp = _get_or_create_rider_profile(db, rider)
    now = _utcnow()
    if rp.last_location_at:
        elapsed = (now - rp.last_location_at).total_seconds()
        if elapsed < get_min_location_interval_seconds():
            return rp
    rp.latitude = latitude
    rp.longitude = longitude
    rp.last_location_at = now
    rp.updated_at = now
    db.commit()
    db.refresh(rp)

    active = get_active_delivery(db, rider)
    if active:
        active.rider_latitude = latitude
        active.rider_longitude = longitude
        active.rider_heading = heading
        active.rider_accuracy_m = accuracy_m
        active.rider_location_at = now
        active.updated_at = now
        db.commit()

    return rp


def get_active_delivery(db: Session, rider: User) -> Optional[Delivery]:
    q = select(Delivery).where(
        Delivery.rider_id == rider.id,
        Delivery.status.in_(
            [
                DeliveryStatus.assigned.value,
                DeliveryStatus.en_route_pickup.value,
                DeliveryStatus.arrived_pickup.value,
                DeliveryStatus.picked_up.value,
                DeliveryStatus.in_transit.value,
            ]
        ),
    )
    return db.scalars(q).first()


def list_available_jobs(db: Session, rider: User, limit: int = 20) -> list[dict]:
    rp = _get_or_create_rider_profile(db, rider)
    if not rp.is_online or not valid_coordinate(rp.latitude, rp.longitude):
        return []

    if get_active_delivery(db, rider):
        return []

    radius = get_dispatch_radius_km()
    min_lat, max_lat, min_lon, max_lon = bounding_box(rp.latitude, rp.longitude, radius)

    rejected_subq = select(RiderJobDecision.order_id).where(
        RiderJobDecision.rider_id == rider.id,
        RiderJobDecision.decision == RiderJobDecisionType.rejected.value,
    )

    q = (
        select(Order, Delivery)
        .join(Delivery, Delivery.order_id == Order.id)
        .where(
            Order.status == OrderStatus.searching_rider.value,
            Delivery.status == DeliveryStatus.searching.value,
            Delivery.rider_id.is_(None),
            Order.pickup_latitude.isnot(None),
            Order.pickup_longitude.isnot(None),
            Order.pickup_latitude >= min_lat,
            Order.pickup_latitude <= max_lat,
            Order.pickup_longitude >= min_lon,
            Order.pickup_longitude <= max_lon,
            Order.id.notin_(rejected_subq),
        )
        .limit(limit * 3)
    )
    rows = db.execute(q).all()
    jobs: list[dict] = []
    for order, delivery in rows:
        dist_km = haversine_km(rp.latitude, rp.longitude, order.pickup_latitude, order.pickup_longitude)
        if dist_km > radius:
            continue
        route = estimate_route(
            rp.latitude,
            rp.longitude,
            order.pickup_latitude,
            order.pickup_longitude,
        )
        jobs.append(
            {
                "order_id": order.id,
                "delivery_id": delivery.id,
                "crop": order.crop,
                "quantity_kg": order.quantity_kg,
                "pickup_district_area": order.pickup_address_label or "Pickup location",
                "delivery_district_area": order.delivery_address_label or "Delivery location",
                "distance_to_pickup_km": round(dist_km, 2),
                "route_distance_m": route.distance_m,
                "route_duration_s": route.duration_s,
                "maps_available": route.available,
            }
        )
    jobs.sort(key=lambda j: j["distance_to_pickup_km"])
    return jobs[:limit]


def reject_job(db: Session, rider: User, order_id: int) -> None:
    order = db.get(Order, order_id)
    if not order or order.status != OrderStatus.searching_rider.value:
        raise ValueError("job not available")
    existing = db.scalars(
        select(RiderJobDecision).where(
            RiderJobDecision.order_id == order_id,
            RiderJobDecision.rider_id == rider.id,
        )
    ).first()
    if existing:
        return
    db.add(
        RiderJobDecision(
            order_id=order_id,
            rider_id=rider.id,
            decision=RiderJobDecisionType.rejected.value,
        )
    )
    db.commit()


def accept_job(db: Session, rider: User, order_id: int) -> Delivery:
    if get_active_delivery(db, rider):
        raise ValueError("rider already has an active delivery")

    rp = _get_or_create_rider_profile(db, rider)
    if not rp.is_online or not valid_coordinate(rp.latitude, rp.longitude):
        raise ValueError("rider must be online with valid location")

    stale_seconds = get_location_stale_seconds()
    if rp.last_location_at and (_utcnow() - rp.last_location_at).total_seconds() > stale_seconds:
        raise ValueError("rider location is stale — update GPS first")

    order = db.execute(select(Order).where(Order.id == order_id).with_for_update()).scalar_one_or_none()
    if not order or order.status != OrderStatus.searching_rider.value:
        raise ValueError("job not available")

    delivery = db.execute(select(Delivery).where(Delivery.order_id == order_id).with_for_update()).scalar_one_or_none()
    if not delivery or delivery.status != DeliveryStatus.searching.value or delivery.rider_id is not None:
        raise ValueError("job already assigned")

    route = estimate_route(
        order.pickup_latitude,
        order.pickup_longitude,
        order.delivery_latitude,
        order.delivery_longitude,
    )

    now = _utcnow()
    delivery.rider_id = rider.id
    delivery.status = DeliveryStatus.assigned.value
    delivery.assigned_at = now
    delivery.route_distance_m = route.distance_m
    delivery.route_duration_s = route.duration_s
    delivery.route_polyline = route.polyline
    delivery.rider_latitude = rp.latitude
    delivery.rider_longitude = rp.longitude
    delivery.rider_location_at = rp.last_location_at
    delivery.updated_at = now

    _transition_order(db, order, OrderStatus.rider_assigned.value, actor=rider)
    _record_event(db, order, "rider_assigned", actor=rider, detail=f"rider_id={rider.id}")

    db.commit()
    db.refresh(delivery)
    return delivery


def advance_delivery_status(db: Session, rider: User, delivery_id: int, new_status: str) -> Delivery:
    delivery = db.get(Delivery, delivery_id)
    if not delivery or delivery.rider_id != rider.id:
        raise ValueError("delivery not found")

    allowed = _DELIVERY_TRANSITIONS.get(delivery.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal delivery transition {delivery.status} -> {new_status}")

    now = _utcnow()
    delivery.status = new_status
    delivery.updated_at = now
    if new_status == DeliveryStatus.picked_up.value:
        delivery.picked_up_at = now
    if new_status == DeliveryStatus.delivered.value:
        delivery.delivered_at = now

    order = db.get(Order, delivery.order_id)
    if order and new_status in _ORDER_FOR_DELIVERY:
        _transition_order(db, order, _ORDER_FOR_DELIVERY[new_status], actor=rider)

    db.commit()
    db.refresh(delivery)
    return delivery


def list_rider_deliveries(db: Session, rider: User, active_only: bool = False, limit: int = 20) -> list[Delivery]:
    q = select(Delivery).where(Delivery.rider_id == rider.id)
    if active_only:
        q = q.where(
            Delivery.status.in_(
                [
                    DeliveryStatus.assigned.value,
                    DeliveryStatus.en_route_pickup.value,
                    DeliveryStatus.arrived_pickup.value,
                    DeliveryStatus.picked_up.value,
                    DeliveryStatus.in_transit.value,
                ]
            )
        )
    q = q.order_by(Delivery.updated_at.desc()).limit(limit)
    return list(db.scalars(q).all())


def get_delivery_detail(db: Session, delivery_id: int, actor: User) -> dict:
    delivery = db.get(Delivery, delivery_id)
    if not delivery:
        raise ValueError("delivery not found")
    order = db.get(Order, delivery.order_id)
    if not order:
        raise ValueError("order not found")

    if actor.role == UserRole.rider.value:
        if delivery.rider_id != actor.id:
            raise ValueError("not your delivery")
    elif actor.role == UserRole.buyer.value:
        if order.buyer_id != actor.id:
            raise ValueError("not your order")
    elif actor.role == UserRole.farmer.value:
        if order.farmer_id != actor.id:
            raise ValueError("not your order")
    else:
        raise ValueError("access denied")

    show_exact = actor.role == UserRole.rider.value or (
        actor.role in {UserRole.buyer.value, UserRole.farmer.value}
        and delivery.rider_id is not None
        and order.status
        not in {OrderStatus.searching_rider.value, OrderStatus.pending_farmer_confirmation.value}
    )

    return {
        "delivery_id": delivery.id,
        "order_id": order.id,
        "status": delivery.status,
        "order_status": order.status,
        "crop": order.crop,
        "quantity_kg": order.quantity_kg,
        "pickup": {
            "address_label": order.pickup_address_label if show_exact else (order.pickup_address_label or "Pickup area"),
            "latitude": order.pickup_latitude if show_exact else None,
            "longitude": order.pickup_longitude if show_exact else None,
        },
        "delivery": {
            "address_label": order.delivery_address_label if show_exact else (order.delivery_address_label or "Delivery area"),
            "latitude": order.delivery_latitude if show_exact else None,
            "longitude": order.delivery_longitude if show_exact else None,
        },
        "route_polyline": delivery.route_polyline,
        "route_distance_m": delivery.route_distance_m,
        "route_duration_s": delivery.route_duration_s,
        "rider_latitude": delivery.rider_latitude,
        "rider_longitude": delivery.rider_longitude,
        "rider_heading": delivery.rider_heading,
        "rider_location_at": delivery.rider_location_at.isoformat() if delivery.rider_location_at else None,
    }
