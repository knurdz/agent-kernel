"""Rider dispatch endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user
from marketplace.database import get_db
from marketplace.dispatch_service import (
    accept_job,
    advance_delivery_status,
    get_active_delivery,
    get_delivery_detail,
    list_available_jobs,
    list_rider_deliveries,
    reject_job,
    set_rider_online,
    update_rider_location,
)
from marketplace.models import User
from marketplace.notifications import notify_delivery_update
from marketplace.order_serializers import order_to_response
from marketplace.order_service import confirm_handoff, get_order, get_order_tracking
from marketplace.schemas import (
    DeliveryStatusUpdate,
    HandoffConfirm,
    OrderResponse,
    RiderJobAccept,
    RiderJobOut,
    RiderLocationUpdate,
    RiderOnlineUpdate,
    TrackingResponse,
)

router = APIRouter(prefix="/api/rider", tags=["rider"])


def _rider(user: User = Depends(get_current_user)) -> User:
    if user.role != "rider":
        raise HTTPException(status_code=403, detail="rider role required")
    return user


@router.post("/online")
def set_online(payload: RiderOnlineUpdate, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    try:
        rp = set_rider_online(db, rider, payload.online)
        return {"is_online": rp.is_online}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/location")
def post_location(payload: RiderLocationUpdate, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    try:
        rp = update_rider_location(
            db,
            rider,
            payload.latitude,
            payload.longitude,
            heading=payload.heading,
            accuracy_m=payload.accuracy_m,
        )
        return {
            "latitude": rp.latitude,
            "longitude": rp.longitude,
            "last_location_at": rp.last_location_at.isoformat() if rp.last_location_at else None,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/jobs", response_model=list[RiderJobOut])
def get_jobs(db: Session = Depends(get_db), rider: User = Depends(_rider)):
    return list_available_jobs(db, rider)


@router.post("/jobs/{order_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject(order_id: int, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    try:
        reject_job(db, rider, order_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return None


@router.post("/jobs/{order_id}/accept")
def accept(
    order_id: int,
    payload: RiderJobAccept = RiderJobAccept(),
    db: Session = Depends(get_db),
    rider: User = Depends(_rider),
):
    try:
        if payload.latitude is not None and payload.longitude is not None:
            update_rider_location(
                db,
                rider,
                payload.latitude,
                payload.longitude,
                accuracy_m=payload.accuracy_m,
            )
        delivery = accept_job(db, rider, order_id)
        order = get_order(db, order_id)
        if order:
            notify_delivery_update(order.buyer_id, order.id, "rider_assigned", "A rider accepted your delivery")
            notify_delivery_update(order.farmer_id, order.id, "rider_assigned", "A rider is on the way")
        return get_delivery_detail(db, delivery.id, rider)
    except ValueError as exc:
        raise HTTPException(status_code=409 if "already" in str(exc) else 400, detail=str(exc)) from exc


@router.get("/deliveries/active")
def get_active(db: Session = Depends(get_db), rider: User = Depends(_rider)):
    delivery = get_active_delivery(db, rider)
    if not delivery:
        return None
    return get_delivery_detail(db, delivery.id, rider)


@router.get("/deliveries")
def list_deliveries(active_only: bool = False, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    deliveries = list_rider_deliveries(db, rider, active_only=active_only)
    return [get_delivery_detail(db, d.id, rider) for d in deliveries]


@router.get("/deliveries/{delivery_id}")
def get_delivery(delivery_id: int, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    try:
        return get_delivery_detail(db, delivery_id, rider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/deliveries/{delivery_id}/status")
def update_status(
    delivery_id: int,
    payload: DeliveryStatusUpdate,
    db: Session = Depends(get_db),
    rider: User = Depends(_rider),
):
    try:
        delivery = advance_delivery_status(db, rider, delivery_id, payload.status)
        order = get_order(db, delivery.order_id)
        if order:
            msg = f"Delivery update: {payload.status.replace('_', ' ')}"
            notify_delivery_update(order.buyer_id, order.id, payload.status, msg)
            notify_delivery_update(order.farmer_id, order.id, payload.status, msg)
        return get_delivery_detail(db, delivery.id, rider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/orders/{order_id}/tracking", response_model=TrackingResponse)
def get_order_tracking_endpoint(order_id: int, db: Session = Depends(get_db), rider: User = Depends(_rider)):
    try:
        return get_order_tracking(db, order_id, rider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/orders/{order_id}/confirm-handoff", response_model=OrderResponse)
def confirm_handoff_endpoint(
    order_id: int,
    payload: HandoffConfirm,
    db: Session = Depends(get_db),
    rider: User = Depends(_rider),
):
    try:
        order = confirm_handoff(db, actor=rider, order_id=order_id, pin=payload.pin)
        notify_delivery_update(order.buyer_id, order.id, "delivered", f"Your {order.crop} order was delivered")
        return order_to_response(order)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
