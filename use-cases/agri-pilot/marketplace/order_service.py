"""Order lifecycle service — deterministic state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.delivery_utils import (
    generate_handoff_pin,
    hash_handoff_pin,
    resolve_farmer_pickup,
    valid_coordinate,
    verify_handoff_pin,
)
from marketplace.models import (
    ConnectionRequest,
    Delivery,
    DeliveryStatus,
    FarmerProfile,
    FulfillmentMode,
    Listing,
    ListingStatus,
    Order,
    OrderEvent,
    OrderStatus,
    RiderProfile,
    User,
    UserRole,
)

# Legal order transitions keyed by current status
_ORDER_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.pending_farmer_confirmation.value: {
        OrderStatus.confirmed.value,
        OrderStatus.farmer_rejected.value,
        OrderStatus.cancelled.value,
    },
    OrderStatus.confirmed.value: {OrderStatus.ready.value, OrderStatus.cancelled.value},
    OrderStatus.ready.value: {
        OrderStatus.searching_rider.value,
        OrderStatus.delivered.value,
        OrderStatus.cancelled.value,
    },
    OrderStatus.searching_rider.value: {
        OrderStatus.rider_assigned.value,
        OrderStatus.cancelled.value,
    },
    OrderStatus.rider_assigned.value: {
        OrderStatus.en_route_pickup.value,
        OrderStatus.cancelled.value,
    },
    OrderStatus.en_route_pickup.value: {OrderStatus.arrived_pickup.value, OrderStatus.cancelled.value},
    OrderStatus.arrived_pickup.value: {OrderStatus.picked_up.value, OrderStatus.cancelled.value},
    OrderStatus.picked_up.value: {OrderStatus.in_transit.value, OrderStatus.cancelled.value},
    OrderStatus.in_transit.value: {OrderStatus.delivered.value, OrderStatus.cancelled.value},
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _record_event(
    db: Session,
    order: Order,
    event_type: str,
    actor: Optional[User] = None,
    detail: Optional[str] = None,
) -> None:
    db.add(
        OrderEvent(
            order_id=order.id,
            actor_id=actor.id if actor else None,
            actor_role=actor.role if actor else None,
            event_type=event_type,
            detail=detail,
        )
    )


def _available_quantity(listing: Listing) -> float:
    return float(listing.quantity_kg) - float(listing.reserved_quantity_kg or 0)


def _reserve_quantity(db: Session, listing: Listing, qty: float) -> None:
    available = _available_quantity(listing)
    if qty > available + 0.001:
        raise ValueError(f"insufficient quantity: requested {qty}kg, available {available}kg")
    listing.reserved_quantity_kg = float(listing.reserved_quantity_kg or 0) + qty


def _release_quantity(db: Session, listing: Listing, qty: float) -> None:
    listing.reserved_quantity_kg = max(0.0, float(listing.reserved_quantity_kg or 0) - qty)


def _finalize_quantity(db: Session, listing: Listing, qty: float) -> None:
    listing.reserved_quantity_kg = max(0.0, float(listing.reserved_quantity_kg or 0) - qty)
    listing.quantity_kg = max(0.0, float(listing.quantity_kg) - qty)
    if listing.quantity_kg <= 0.001:
        listing.quantity_kg = 0.0
        listing.status = ListingStatus.sold.value
    elif _available_quantity(listing) <= 0.001 and listing.status == ListingStatus.active.value:
        listing.status = ListingStatus.sold.value


def _transition_order(db: Session, order: Order, new_status: str, actor: Optional[User] = None, detail: Optional[str] = None) -> Order:
    allowed = _ORDER_TRANSITIONS.get(order.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {order.status} -> {new_status}")
    order.status = new_status
    order.updated_at = _utcnow()
    _record_event(db, order, f"status:{new_status}", actor=actor, detail=detail)
    return order


def get_order(db: Session, order_id: int) -> Optional[Order]:
    return db.get(Order, order_id)


def list_buyer_orders(db: Session, buyer_id: int, limit: int = 20, offset: int = 0) -> list[Order]:
    q = select(Order).where(Order.buyer_id == buyer_id).order_by(Order.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


def list_farmer_orders(db: Session, farmer_id: int, limit: int = 20, offset: int = 0) -> list[Order]:
    q = select(Order).where(Order.farmer_id == farmer_id).order_by(Order.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


def _mark_listing_sold_if_depleted(listing: Listing) -> None:
    if _available_quantity(listing) <= 0.001 and listing.status == ListingStatus.active.value:
        listing.status = ListingStatus.sold.value


def _resolve_connection_and_listing(
    db: Session,
    *,
    buyer: User,
    listing_id: Optional[int] = None,
    connection_id: Optional[int] = None,
) -> tuple[ConnectionRequest, Listing]:
    if (listing_id is None) == (connection_id is None):
        raise ValueError("provide exactly one of listing_id or connection_id")

    if listing_id is not None:
        listing = db.execute(select(Listing).where(Listing.id == listing_id).with_for_update()).scalar_one_or_none()
        if not listing or listing.status != ListingStatus.active.value:
            raise ValueError("listing not available")
        if listing.farmer_id == buyer.id:
            raise ValueError("cannot order own listing")
        conn = ConnectionRequest(
            listing_id=listing.id,
            buyer_id=buyer.id,
            status="accepted",
            message="Direct buy",
        )
        db.add(conn)
        db.flush()
        return conn, listing

    conn = db.get(ConnectionRequest, connection_id)
    if not conn or conn.buyer_id != buyer.id:
        raise ValueError("connection not found")
    if conn.status == "pending":
        conn.status = "accepted"
        conn.updated_at = _utcnow()
    elif conn.status not in {"accepted", "completed"}:
        raise ValueError("connection not available")

    existing = db.scalars(select(Order).where(Order.connection_id == connection_id)).first()
    if existing:
        raise ValueError("order already exists for this connection")

    listing = db.execute(select(Listing).where(Listing.id == conn.listing_id).with_for_update()).scalar_one_or_none()
    if not listing or listing.status != ListingStatus.active.value:
        raise ValueError("listing not available")
    return conn, listing


def _persist_farmer_pickup_profile(
    db: Session,
    fp: FarmerProfile | None,
    lat: float,
    lon: float,
    label: Optional[str],
) -> None:
    """Cache resolved pickup coords on the farmer profile when GPS was missing."""
    if fp is None or valid_coordinate(fp.latitude, fp.longitude):
        return
    if not valid_coordinate(lat, lon):
        return
    fp.latitude = lat
    fp.longitude = lon
    if label and not fp.address_label:
        fp.address_label = label


def _create_delivery_search(db: Session, order: Order, *, actor: User) -> None:
    delivery = Delivery(
        order_id=order.id,
        status=DeliveryStatus.searching.value,
    )
    db.add(delivery)
    db.flush()
    _transition_order(db, order, OrderStatus.searching_rider.value, actor=actor)
    delivery.status = DeliveryStatus.searching.value


def _dispatch_delivery_order(
    db: Session,
    order: Order,
    *,
    actor: User,
    require_coords: bool = True,
) -> None:
    """Advance a delivery order to searching_rider when pickup coordinates are known."""
    if order.fulfillment_mode != FulfillmentMode.delivery.value:
        return
    if not valid_coordinate(order.pickup_latitude, order.pickup_longitude):
        if require_coords:
            raise ValueError("farmer pickup location missing — set farm district or pin")
        return

    if order.status == OrderStatus.pending_farmer_confirmation.value:
        _transition_order(db, order, OrderStatus.confirmed.value, actor=actor, detail="auto-confirmed")
    if order.status == OrderStatus.confirmed.value:
        _transition_order(db, order, OrderStatus.ready.value, actor=actor)
    if order.status == OrderStatus.ready.value:
        _create_delivery_search(db, order, actor=actor)


def create_order(
    db: Session,
    *,
    buyer: User,
    quantity_kg: float,
    fulfillment_mode: str,
    connection_id: Optional[int] = None,
    listing_id: Optional[int] = None,
    delivery_address_label: Optional[str] = None,
    delivery_latitude: Optional[float] = None,
    delivery_longitude: Optional[float] = None,
) -> tuple[Order, Optional[str]]:
    """Buyer creates order directly from a listing or legacy connection."""
    if buyer.role != UserRole.buyer.value:
        raise ValueError("buyer role required")
    if quantity_kg <= 0:
        raise ValueError("quantity_kg must be > 0")
    if fulfillment_mode not in {FulfillmentMode.pickup.value, FulfillmentMode.delivery.value}:
        raise ValueError("invalid fulfillment_mode")

    conn, listing = _resolve_connection_and_listing(
        db,
        buyer=buyer,
        listing_id=listing_id,
        connection_id=connection_id,
    )

    farmer = db.get(User, listing.farmer_id)
    if not farmer:
        raise ValueError("farmer not found")

    fp = farmer.farmer_profile
    pickup_lat, pickup_lon, pickup_label = resolve_farmer_pickup(fp)

    if fulfillment_mode == FulfillmentMode.delivery.value:
        if not valid_coordinate(delivery_latitude, delivery_longitude):
            raise ValueError("delivery coordinates required for delivery mode")
        if not delivery_address_label:
            raise ValueError("delivery address required")
        if not valid_coordinate(pickup_lat, pickup_lon):
            raise ValueError("farmer pickup location missing — set farm district or pin")

    _reserve_quantity(db, listing, quantity_kg)
    _mark_listing_sold_if_depleted(listing)

    pin_plain = generate_handoff_pin()
    order = Order(
        connection_id=conn.id,
        listing_id=listing.id,
        buyer_id=buyer.id,
        farmer_id=farmer.id,
        crop=listing.crop,
        quantity_kg=float(quantity_kg),
        price_per_kg=listing.price_per_kg,
        fulfillment_mode=fulfillment_mode,
        status=OrderStatus.pending_farmer_confirmation.value,
        pickup_address_label=pickup_label,
        pickup_latitude=pickup_lat,
        pickup_longitude=pickup_lon,
        delivery_address_label=delivery_address_label,
        delivery_latitude=delivery_latitude,
        delivery_longitude=delivery_longitude,
        handoff_pin_hash=hash_handoff_pin(pin_plain),
    )
    db.add(order)
    db.flush()
    _record_event(db, order, "created", actor=buyer, detail=f"mode={fulfillment_mode}")
    if fulfillment_mode == FulfillmentMode.delivery.value:
        _persist_farmer_pickup_profile(db, fp, pickup_lat, pickup_lon, pickup_label)
        _dispatch_delivery_order(db, order, actor=buyer, require_coords=True)
    db.commit()
    db.refresh(order)
    return order, pin_plain


def farmer_confirm_order(
    db: Session,
    *,
    farmer: User,
    order_id: int,
    confirmed_quantity_kg: float,
    pickup_address_label: Optional[str] = None,
    pickup_latitude: Optional[float] = None,
    pickup_longitude: Optional[float] = None,
) -> Order:
    order = db.get(Order, order_id)
    if not order or order.farmer_id != farmer.id:
        raise ValueError("order not found")
    if order.status != OrderStatus.pending_farmer_confirmation.value:
        raise ValueError("order not awaiting confirmation")
    if confirmed_quantity_kg <= 0:
        raise ValueError("quantity must be > 0")

    listing = db.execute(select(Listing).where(Listing.id == order.listing_id).with_for_update()).scalar_one()
    old_qty = float(order.quantity_kg)
    new_qty = float(confirmed_quantity_kg)
    if abs(new_qty - old_qty) > 0.001:
        _release_quantity(db, listing, old_qty)
        _reserve_quantity(db, listing, new_qty)
        _mark_listing_sold_if_depleted(listing)

    order.quantity_kg = new_qty
    farmer = db.get(User, order.farmer_id)
    fp = farmer.farmer_profile if farmer else None
    lat_override = pickup_latitude if valid_coordinate(pickup_latitude, pickup_longitude) else order.pickup_latitude
    lon_override = pickup_longitude if valid_coordinate(pickup_latitude, pickup_longitude) else order.pickup_longitude
    resolved_lat, resolved_lon, resolved_label = resolve_farmer_pickup(
        fp,
        override_lat=lat_override,
        override_lon=lon_override,
        override_label=pickup_address_label or order.pickup_address_label,
    )
    if valid_coordinate(resolved_lat, resolved_lon):
        order.pickup_latitude = resolved_lat
        order.pickup_longitude = resolved_lon
        if resolved_label:
            order.pickup_address_label = resolved_label

    if order.fulfillment_mode == FulfillmentMode.delivery.value and not valid_coordinate(
        order.pickup_latitude, order.pickup_longitude
    ):
        raise ValueError("farmer pickup location missing — set farm district or pin")

    _transition_order(db, order, OrderStatus.confirmed.value, actor=farmer)
    if order.fulfillment_mode == FulfillmentMode.delivery.value:
        _persist_farmer_pickup_profile(db, fp, order.pickup_latitude, order.pickup_longitude, order.pickup_address_label)
        _dispatch_delivery_order(db, order, actor=farmer, require_coords=True)
    db.commit()
    db.refresh(order)
    return order


def farmer_reject_order(db: Session, *, farmer: User, order_id: int, reason: Optional[str] = None) -> Order:
    order = db.get(Order, order_id)
    if not order or order.farmer_id != farmer.id:
        raise ValueError("order not found")
    if order.status != OrderStatus.pending_farmer_confirmation.value:
        raise ValueError("order not awaiting confirmation")
    listing = db.execute(select(Listing).where(Listing.id == order.listing_id).with_for_update()).scalar_one()
    _release_quantity(db, listing, order.quantity_kg)
    order.cancellation_reason = reason
    _transition_order(db, order, OrderStatus.farmer_rejected.value, actor=farmer, detail=reason)
    db.commit()
    db.refresh(order)
    return order


def farmer_mark_ready(db: Session, *, farmer: User, order_id: int) -> Order:
    order = db.get(Order, order_id)
    if not order or order.farmer_id != farmer.id:
        raise ValueError("order not found")
    if order.status != OrderStatus.confirmed.value:
        raise ValueError("order must be confirmed first")

    _transition_order(db, order, OrderStatus.ready.value, actor=farmer)

    if order.fulfillment_mode == FulfillmentMode.delivery.value:
        delivery = Delivery(
            order_id=order.id,
            status=DeliveryStatus.searching.value,
        )
        db.add(delivery)
        db.flush()
        _transition_order(db, order, OrderStatus.searching_rider.value, actor=farmer)
        delivery.status = DeliveryStatus.searching.value

    db.commit()
    db.refresh(order)
    return order


def cancel_order(db: Session, *, actor: User, order_id: int, reason: Optional[str] = None) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise ValueError("order not found")

    cancellable = {
        OrderStatus.pending_farmer_confirmation.value,
        OrderStatus.confirmed.value,
        OrderStatus.ready.value,
        OrderStatus.searching_rider.value,
    }
    if order.status not in cancellable:
        raise ValueError("order cannot be cancelled in current status")

    if actor.role == UserRole.buyer.value and order.buyer_id != actor.id:
        raise ValueError("not your order")
    if actor.role == UserRole.farmer.value and order.farmer_id != actor.id:
        raise ValueError("not your order")

    if order.status in {
        OrderStatus.pending_farmer_confirmation.value,
        OrderStatus.confirmed.value,
        OrderStatus.ready.value,
        OrderStatus.searching_rider.value,
    }:
        listing = db.execute(select(Listing).where(Listing.id == order.listing_id).with_for_update()).scalar_one()
        _release_quantity(db, listing, order.quantity_kg)

    order.cancellation_reason = reason
    _transition_order(db, order, OrderStatus.cancelled.value, actor=actor, detail=reason)

    if order.delivery:
        order.delivery.status = DeliveryStatus.cancelled.value

    db.commit()
    db.refresh(order)
    return order


def confirm_handoff(
    db: Session,
    *,
    actor: User,
    order_id: int,
    pin: str,
) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise ValueError("order not found")

    terminal_ready = {
        OrderStatus.ready.value,
        OrderStatus.in_transit.value,
        OrderStatus.picked_up.value,
    }
    if order.status not in terminal_ready:
        raise ValueError("order not ready for handoff confirmation")

    if not order.handoff_pin_hash or not verify_handoff_pin(pin, order.handoff_pin_hash):
        raise ValueError("invalid handoff PIN")

    if actor.role == UserRole.buyer.value and order.buyer_id != actor.id:
        raise ValueError("not your order")
    if actor.role == UserRole.rider.value and (not order.delivery or order.delivery.rider_id != actor.id):
        raise ValueError("not your delivery")

    listing = db.execute(select(Listing).where(Listing.id == order.listing_id).with_for_update()).scalar_one()
    _finalize_quantity(db, listing, order.quantity_kg)

    _transition_order(db, order, OrderStatus.delivered.value, actor=actor)
    if order.delivery:
        order.delivery.status = DeliveryStatus.delivered.value
        order.delivery.delivered_at = _utcnow()

    conn = db.get(ConnectionRequest, order.connection_id)
    if conn and conn.status == "accepted":
        conn.status = "completed"
        conn.updated_at = _utcnow()

    db.commit()
    db.refresh(order)
    return order


def get_order_tracking(db: Session, order_id: int, actor: User) -> dict:
    order = db.get(Order, order_id)
    if not order:
        raise ValueError("order not found")

    if actor.role == UserRole.buyer.value and order.buyer_id != actor.id:
        raise ValueError("not your order")
    if actor.role == UserRole.farmer.value and order.farmer_id != actor.id:
        raise ValueError("not your order")
    if actor.role == UserRole.rider.value and (not order.delivery or order.delivery.rider_id != actor.id):
        raise ValueError("not your delivery")

    delivery = order.delivery
    from marketplace.delivery_utils import get_location_stale_seconds
    from marketplace.tracking_service import (
        compute_live_leg,
        party_snapshot,
        refresh_delivery_route,
        show_party_phones,
    )

    if delivery and delivery.rider_id is not None:
        refresh_delivery_route(db, delivery, order)
        db.flush()
        db.refresh(delivery)

    stale_seconds = get_location_stale_seconds()
    rider_stale = True
    if delivery and delivery.rider_location_at:
        age = (_utcnow() - _as_utc(delivery.rider_location_at)).total_seconds()
        rider_stale = age > stale_seconds

    include_phones = show_party_phones(order, delivery)
    farmer_user = db.get(User, order.farmer_id)
    buyer_user = db.get(User, order.buyer_id)
    rider_user = db.get(User, delivery.rider_id) if delivery and delivery.rider_id else None

    live_leg = compute_live_leg(delivery, order)
    estimated_total = None
    if order.price_per_kg is not None:
        estimated_total = round(order.price_per_kg * order.quantity_kg, 2)

    maps_available = bool(live_leg.get("route_polyline"))

    return {
        "order_id": order.id,
        "delivery_id": delivery.id if delivery else None,
        "status": order.status,
        "fulfillment_mode": order.fulfillment_mode,
        "quantity_kg": order.quantity_kg,
        "crop": order.crop,
        "price_per_kg": order.price_per_kg,
        "estimated_total": estimated_total,
        "created_at": order.created_at,
        "assigned_at": delivery.assigned_at if delivery else None,
        "picked_up_at": delivery.picked_up_at if delivery else None,
        "delivered_at": delivery.delivered_at if delivery else None,
        "pickup": {
            "address_label": order.pickup_address_label,
            "latitude": order.pickup_latitude,
            "longitude": order.pickup_longitude,
        },
        "delivery": {
            "address_label": order.delivery_address_label,
            "latitude": order.delivery_latitude,
            "longitude": order.delivery_longitude,
        },
        "farmer": party_snapshot(farmer_user, include_phone=include_phones),
        "buyer": party_snapshot(buyer_user, include_phone=include_phones),
        "rider": {
            "id": delivery.rider_id if delivery else None,
            "name": rider_user.name if rider_user else None,
            "phone": rider_user.phone_number if rider_user and include_phones else None,
            "latitude": delivery.rider_latitude if delivery else None,
            "longitude": delivery.rider_longitude if delivery else None,
            "heading": delivery.rider_heading if delivery else None,
            "accuracy_m": delivery.rider_accuracy_m if delivery else None,
            "location_at": delivery.rider_location_at.isoformat() if delivery and delivery.rider_location_at else None,
            "stale": rider_stale,
        },
        "delivery_status": delivery.status if delivery else None,
        "next_stop": live_leg["next_stop"],
        "remaining_distance_m": live_leg["remaining_distance_m"],
        "remaining_duration_s": live_leg["remaining_duration_s"],
        "route_polyline": live_leg["route_polyline"],
        "route_distance_m": delivery.route_distance_m if delivery else None,
        "route_duration_s": delivery.route_duration_s if delivery else None,
        "maps_available": maps_available,
        "events": [
            {"event_type": e.event_type, "detail": e.detail, "created_at": e.created_at.isoformat()}
            for e in (order.events or [])
        ],
    }
