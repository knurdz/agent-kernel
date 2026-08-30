"""Order lifecycle service — deterministic state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from marketplace.delivery_utils import (
    generate_handoff_pin,
    hash_handoff_pin,
    valid_coordinate,
    verify_handoff_pin,
)
from marketplace.models import (
    ConnectionRequest,
    Delivery,
    DeliveryStatus,
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


def create_order(
    db: Session,
    *,
    buyer: User,
    connection_id: int,
    quantity_kg: float,
    fulfillment_mode: str,
    delivery_address_label: Optional[str] = None,
    delivery_latitude: Optional[float] = None,
    delivery_longitude: Optional[float] = None,
) -> tuple[Order, Optional[str]]:
    """Buyer creates order from accepted connection. Returns (order, handoff_pin_plain)."""
    if buyer.role != UserRole.buyer.value:
        raise ValueError("buyer role required")
    if quantity_kg <= 0:
        raise ValueError("quantity_kg must be > 0")
    if fulfillment_mode not in {FulfillmentMode.pickup.value, FulfillmentMode.delivery.value}:
        raise ValueError("invalid fulfillment_mode")

    conn = db.get(ConnectionRequest, connection_id)
    if not conn or conn.buyer_id != buyer.id:
        raise ValueError("connection not found")
    if conn.status != "accepted":
        raise ValueError("connection must be accepted before ordering")

    existing = db.scalars(select(Order).where(Order.connection_id == connection_id)).first()
    if existing:
        raise ValueError("order already exists for this connection")

    listing = db.get(Listing, conn.listing_id)
    if not listing or listing.status != ListingStatus.active.value:
        raise ValueError("listing not available")

    farmer = db.get(User, listing.farmer_id)
    if not farmer:
        raise ValueError("farmer not found")

    fp = farmer.farmer_profile
    pickup_lat = fp.latitude if fp else None
    pickup_lon = fp.longitude if fp else None
    pickup_label = fp.address_label if fp else None

    if fulfillment_mode == FulfillmentMode.delivery.value:
        if not valid_coordinate(delivery_latitude, delivery_longitude):
            raise ValueError("delivery coordinates required for delivery mode")
        if not delivery_address_label:
            raise ValueError("delivery address required")

    pin_plain = generate_handoff_pin()
    order = Order(
        connection_id=connection_id,
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

    listing = db.get(Listing, order.listing_id)
    if not listing:
        raise ValueError("listing not found")

    listing = db.execute(select(Listing).where(Listing.id == order.listing_id).with_for_update()).scalar_one()
    _reserve_quantity(db, listing, confirmed_quantity_kg)

    order.quantity_kg = float(confirmed_quantity_kg)
    if pickup_address_label:
        order.pickup_address_label = pickup_address_label
    if valid_coordinate(pickup_latitude, pickup_longitude):
        order.pickup_latitude = pickup_latitude
        order.pickup_longitude = pickup_longitude

    if order.fulfillment_mode == FulfillmentMode.delivery.value and not valid_coordinate(
        order.pickup_latitude, order.pickup_longitude
    ):
        raise ValueError("farmer pickup coordinates required for delivery orders")

    _transition_order(db, order, OrderStatus.confirmed.value, actor=farmer)
    db.commit()
    db.refresh(order)
    return order


def farmer_reject_order(db: Session, *, farmer: User, order_id: int, reason: Optional[str] = None) -> Order:
    order = db.get(Order, order_id)
    if not order or order.farmer_id != farmer.id:
        raise ValueError("order not found")
    if order.status != OrderStatus.pending_farmer_confirmation.value:
        raise ValueError("order not awaiting confirmation")
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

    if order.status in {OrderStatus.confirmed.value, OrderStatus.ready.value, OrderStatus.searching_rider.value}:
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

    stale_seconds = get_location_stale_seconds()
    rider_stale = True
    if delivery and delivery.rider_location_at:
        age = (_utcnow() - delivery.rider_location_at).total_seconds()
        rider_stale = age > stale_seconds

    return {
        "order_id": order.id,
        "status": order.status,
        "fulfillment_mode": order.fulfillment_mode,
        "quantity_kg": order.quantity_kg,
        "crop": order.crop,
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
        "rider": {
            "id": delivery.rider_id if delivery else None,
            "latitude": delivery.rider_latitude if delivery else None,
            "longitude": delivery.rider_longitude if delivery else None,
            "heading": delivery.rider_heading if delivery else None,
            "accuracy_m": delivery.rider_accuracy_m if delivery else None,
            "location_at": delivery.rider_location_at.isoformat() if delivery and delivery.rider_location_at else None,
            "stale": rider_stale,
            "route_polyline": delivery.route_polyline if delivery else None,
            "route_distance_m": delivery.route_distance_m if delivery else None,
            "route_duration_s": delivery.route_duration_s if delivery else None,
        },
        "delivery_status": delivery.status if delivery else None,
        "events": [
            {"event_type": e.event_type, "detail": e.detail, "created_at": e.created_at.isoformat()}
            for e in (order.events or [])
        ],
    }
