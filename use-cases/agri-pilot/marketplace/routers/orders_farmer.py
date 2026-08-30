"""Farmer order endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user, require_active_subscription
from marketplace.database import get_db
from marketplace.models import User
from marketplace.notifications import notify_delivery_update
from marketplace.order_serializers import order_to_response
from marketplace.order_service import (
    cancel_order,
    farmer_confirm_order,
    farmer_mark_ready,
    farmer_reject_order,
    get_order,
    get_order_tracking,
    list_farmer_orders,
)
from marketplace.schemas import FarmerConfirmOrder, OrderReject, OrderResponse, TrackingResponse

router = APIRouter(prefix="/api/farmer/orders", tags=["farmer-orders"])


def _farmer(user: User = Depends(get_current_user), _sub=Depends(require_active_subscription)) -> User:
    if user.role != "farmer":
        raise HTTPException(status_code=403, detail="farmer role required")
    return user


@router.get("", response_model=list[OrderResponse])
def get_orders(db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    orders = list_farmer_orders(db, farmer.id)
    return [order_to_response(o) for o in orders]


@router.get("/{order_id}", response_model=OrderResponse)
def get_order_detail(order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    order = get_order(db, order_id)
    if not order or order.farmer_id != farmer.id:
        raise HTTPException(status_code=404, detail="order not found")
    return order_to_response(order)


@router.get("/{order_id}/tracking", response_model=TrackingResponse)
def get_tracking(order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    try:
        return get_order_tracking(db, order_id, farmer)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{order_id}/confirm", response_model=OrderResponse)
def confirm(payload: FarmerConfirmOrder, order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    try:
        order = farmer_confirm_order(
            db,
            farmer=farmer,
            order_id=order_id,
            confirmed_quantity_kg=payload.confirmed_quantity_kg,
            pickup_address_label=payload.pickup_address_label,
            pickup_latitude=payload.pickup_latitude,
            pickup_longitude=payload.pickup_longitude,
        )
        notify_delivery_update(order.buyer_id, order.id, "confirmed", f"Farmer confirmed your {order.crop} order")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{order_id}/reject", response_model=OrderResponse)
def reject(payload: OrderReject, order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    try:
        order = farmer_reject_order(db, farmer=farmer, order_id=order_id, reason=payload.reason)
        notify_delivery_update(order.buyer_id, order.id, "rejected", "Farmer rejected your order")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{order_id}/ready", response_model=OrderResponse)
def mark_ready(order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    try:
        order = farmer_mark_ready(db, farmer=farmer, order_id=order_id)
        notify_delivery_update(order.buyer_id, order.id, "ready", f"Your {order.crop} order is ready")
        if order.fulfillment_mode == "delivery":
            notify_delivery_update(order.buyer_id, order.id, "searching_rider", "Searching for a rider")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{order_id}/cancel", response_model=OrderResponse)
def cancel(payload: OrderReject, order_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer)):
    try:
        order = cancel_order(db, actor=farmer, order_id=order_id, reason=payload.reason)
        notify_delivery_update(order.buyer_id, order.id, "cancelled", "Farmer cancelled the order")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
