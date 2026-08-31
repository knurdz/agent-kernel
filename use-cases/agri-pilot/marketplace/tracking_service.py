"""Live order tracking helpers — route legs, remaining ETA, party info."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from sqlalchemy.orm import Session

from marketplace.delivery_utils import haversine_km, valid_coordinate
from marketplace.maps_service import estimate_route
from marketplace.models import Delivery, DeliveryStatus, Order, OrderStatus, User

ROUTE_REFRESH_INTERVAL_SECONDS = 60
AVERAGE_SPEED_KMH = 30.0

_PICKUP_LEG_STATUSES = {
    DeliveryStatus.assigned.value,
    DeliveryStatus.en_route_pickup.value,
    DeliveryStatus.arrived_pickup.value,
}
_DELIVERY_LEG_STATUSES = {
    DeliveryStatus.picked_up.value,
    DeliveryStatus.in_transit.value,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def next_stop_for_delivery(delivery: Optional[Delivery]) -> Optional[Literal["pickup", "delivery"]]:
    if delivery is None:
        return None
    if delivery.status in _PICKUP_LEG_STATUSES:
        return "pickup"
    if delivery.status in _DELIVERY_LEG_STATUSES:
        return "delivery"
    return None


def _leg_destination(order: Order, next_stop: Literal["pickup", "delivery"]) -> tuple[Optional[float], Optional[float]]:
    if next_stop == "pickup":
        return order.pickup_latitude, order.pickup_longitude
    lat = order.delivery_latitude
    lon = order.delivery_longitude
    if valid_coordinate(lat, lon):
        return lat, lon
    return order.pickup_latitude, order.pickup_longitude


def haversine_remaining(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> tuple[int, int]:
    """Return (remaining_distance_m, remaining_duration_s) from great-circle distance."""
    km = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    distance_m = int(km * 1000)
    duration_s = int(km / AVERAGE_SPEED_KMH * 3600) if km > 0 else 0
    return distance_m, duration_s


def refresh_delivery_route(
    db: Session,
    delivery: Delivery,
    order: Order,
    *,
    force_osrm: bool = False,
) -> None:
    """Refresh stored polyline/ETA for the rider's current leg."""
    next_stop = next_stop_for_delivery(delivery)
    if next_stop is None:
        return

    dest_lat, dest_lon = _leg_destination(order, next_stop)
    if not valid_coordinate(dest_lat, dest_lon):
        return

    origin_lat = delivery.rider_latitude
    origin_lon = delivery.rider_longitude
    if not valid_coordinate(origin_lat, origin_lon):
        origin_lat = order.pickup_latitude
        origin_lon = order.pickup_longitude
    if not valid_coordinate(origin_lat, origin_lon):
        return

    now = _utcnow()
    should_osrm = force_osrm
    if not should_osrm and delivery.route_refreshed_at is not None:
        age = (now - _as_utc(delivery.route_refreshed_at)).total_seconds()
        should_osrm = age >= ROUTE_REFRESH_INTERVAL_SECONDS
    elif delivery.route_refreshed_at is None:
        should_osrm = True

    if should_osrm:
        route = estimate_route(origin_lat, origin_lon, dest_lat, dest_lon)
        delivery.route_distance_m = route.distance_m
        delivery.route_duration_s = route.duration_s
        delivery.route_polyline = route.polyline
        delivery.route_refreshed_at = now
        delivery.updated_at = now


def compute_live_leg(
    delivery: Optional[Delivery],
    order: Order,
) -> dict:
    """Compute next_stop and Haversine remaining distance/duration."""
    next_stop = next_stop_for_delivery(delivery)
    if next_stop is None or delivery is None:
        return {
            "next_stop": next_stop,
            "remaining_distance_m": None,
            "remaining_duration_s": None,
            "route_polyline": delivery.route_polyline if delivery else None,
        }

    dest_lat, dest_lon = _leg_destination(order, next_stop)
    origin_lat = delivery.rider_latitude
    origin_lon = delivery.rider_longitude

    remaining_m: Optional[int] = None
    remaining_s: Optional[int] = None
    if valid_coordinate(origin_lat, origin_lon) and valid_coordinate(dest_lat, dest_lon):
        remaining_m, remaining_s = haversine_remaining(origin_lat, origin_lon, dest_lat, dest_lon)

    return {
        "next_stop": next_stop,
        "remaining_distance_m": remaining_m,
        "remaining_duration_s": remaining_s,
        "route_polyline": delivery.route_polyline,
    }


def party_snapshot(user: Optional[User], *, include_phone: bool) -> Optional[dict]:
    if user is None:
        return None
    party: dict = {"id": user.id, "name": user.name}
    if include_phone:
        party["phone"] = user.phone_number
    return party


def show_party_phones(order: Order, delivery: Optional[Delivery]) -> bool:
    """Expose counterparty phone numbers once a rider is assigned."""
    if delivery is None or delivery.rider_id is None:
        return False
    return order.status not in {
        OrderStatus.searching_rider.value,
        OrderStatus.pending_farmer_confirmation.value,
    }
