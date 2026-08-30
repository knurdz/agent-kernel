"""Buyer order endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user
from marketplace.database import get_db
from marketplace.models import User
from marketplace.notifications import notify_delivery_update
from marketplace.order_serializers import order_to_response
from marketplace.order_service import (
    cancel_order,
    confirm_handoff,
    create_order,
    get_order,
    get_order_tracking,
    list_buyer_orders,
)
from marketplace.schemas import (
    HandoffConfirm,
    OrderCreate,
    OrderCreateResponse,
    OrderReject,
    OrderResponse,
    TrackingResponse,
)

router = APIRouter(prefix="/api/buyer/orders", tags=["buyer-orders"])


def _buyer(user: User = Depends(get_current_user)) -> User:
    if user.role != "buyer":
        raise HTTPException(status_code=403, detail="buyer role required")
    return user


@router.post("", status_code=status.HTTP_201_CREATED, response_model=OrderCreateResponse)
def post_order(payload: OrderCreate, db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    try:
        order, pin = create_order(
            db,
            buyer=buyer,
            connection_id=payload.connection_id,
            listing_id=payload.listing_id,
            quantity_kg=payload.quantity_kg,
            fulfillment_mode=payload.fulfillment_mode,
            delivery_address_label=payload.delivery_address_label,
            delivery_latitude=payload.delivery_latitude,
            delivery_longitude=payload.delivery_longitude,
        )
        notify_delivery_update(order.farmer_id, order.id, "new_order", f"New order for {order.crop}")
        return OrderCreateResponse(order=order_to_response(order), handoff_pin=pin)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[OrderResponse])
def get_orders(db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    orders = list_buyer_orders(db, buyer.id)
    return [order_to_response(o) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_detail(order_id: int, db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    order = get_order(db, order_id)
    if not order or order.buyer_id != buyer.id:
        raise HTTPException(status_code=404, detail="order not found")
    return order_to_response(order)


@router.get("/{order_id}/tracking", response_model=TrackingResponse)
def get_tracking(order_id: int, db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    try:
        return get_order_tracking(db, order_id, buyer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel(payload: OrderReject, order_id: int, db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    try:
        order = cancel_order(db, actor=buyer, order_id=order_id, reason=payload.reason)
        notify_delivery_update(order.farmer_id, order.id, "cancelled", "Buyer cancelled the order")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{order_id}/confirm-handoff", response_model=OrderResponse)
def confirm(payload: HandoffConfirm, order_id: int, db: Session = Depends(get_db), buyer: User = Depends(_buyer)):
    try:
        order = confirm_handoff(db, actor=buyer, order_id=order_id, pin=payload.pin)
        notify_delivery_update(order.farmer_id, order.id, "delivered", f"Order for {order.crop} delivered")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
