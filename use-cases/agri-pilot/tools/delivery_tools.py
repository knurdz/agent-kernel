"""Read-only delivery/order tools for chat (session-bound, guarded)."""

from __future__ import annotations

from typing import Any, Optional

from tools.marketplace_tools import _get_session_identity
from tools.tool_guard import guarded


def _rider_delivery_summary(detail: dict) -> dict[str, Any]:
    pickup = detail.get("pickup") or {}
    delivery = detail.get("delivery") or {}
    return {
        "delivery_id": detail.get("delivery_id"),
        "order_id": detail.get("order_id"),
        "status": detail.get("status"),
        "order_status": detail.get("order_status"),
        "crop": detail.get("crop"),
        "quantity_kg": detail.get("quantity_kg"),
        "pickup_label": pickup.get("address_label"),
        "delivery_label": delivery.get("address_label"),
        "route_duration_s": detail.get("route_duration_s"),
        "route_distance_m": detail.get("route_distance_m"),
    }


def _nearby_jobs_hint(db, user) -> Optional[str]:
    from marketplace.delivery_utils import valid_coordinate
    from marketplace.dispatch_service import _get_or_create_rider_profile, get_active_delivery

    rp = _get_or_create_rider_profile(db, user)
    if get_active_delivery(db, user):
        return "has_active_job"
    if not rp.is_online:
        return "offline"
    if not valid_coordinate(rp.latitude, rp.longitude):
        return "no_gps"
    return "none_nearby"


@guarded
def my_orders_tool(limit: int = 10) -> dict[str, Any]:
    """List the authenticated user's orders (buyer, farmer, or rider view)."""
    uid, role, _sub = _get_session_identity()
    if uid is None:
        return {"ok": False, "error": "not authenticated — log in via the app"}
    from marketplace.database import SessionLocal
    from marketplace.dispatch_service import get_delivery_detail, list_rider_deliveries
    from marketplace.models import User
    from marketplace.order_serializers import order_to_response
    from marketplace.order_service import list_buyer_orders, list_farmer_orders

    db = SessionLocal()
    try:
        if role == "buyer":
            orders = list_buyer_orders(db, uid, limit=limit)
        elif role == "farmer":
            orders = list_farmer_orders(db, uid, limit=limit)
        elif role == "rider":
            user = db.get(User, uid)
            if not user:
                return {"ok": False, "error": "user not found"}
            deliveries = list_rider_deliveries(db, user, limit=limit)
            items = []
            for d in deliveries:
                try:
                    detail = get_delivery_detail(db, d.id, user)
                    items.append(_rider_delivery_summary(detail))
                except ValueError:
                    items.append(
                        {
                            "delivery_id": d.id,
                            "order_id": d.order_id,
                            "status": str(getattr(d.status, "value", d.status)),
                        }
                    )
            return {"ok": True, "role": role, "deliveries": items}
        else:
            return {"ok": False, "error": "role cannot list orders"}
        return {"ok": True, "role": role, "orders": [order_to_response(o).model_dump() for o in orders]}
    finally:
        db.close()


@guarded
def order_status_tool(order_id: int) -> dict[str, Any]:
    """Get delivery tracking snapshot for an order the user participates in."""
    uid, role, _sub = _get_session_identity()
    if uid is None:
        return {"ok": False, "error": "not authenticated"}
    from marketplace.database import SessionLocal
    from marketplace.models import User
    from marketplace.order_service import get_order_tracking

    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if not user:
            return {"ok": False, "error": "user not found"}
        return {"ok": True, "tracking": get_order_tracking(db, order_id, user)}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        db.close()


@guarded
def rider_active_job_tool() -> dict[str, Any]:
    """Return the rider's current active delivery, if any."""
    uid, role, _sub = _get_session_identity()
    if role != "rider" or uid is None:
        return {"ok": False, "error": "rider role required"}
    from marketplace.database import SessionLocal
    from marketplace.models import User
    from marketplace.dispatch_service import get_active_delivery, get_delivery_detail

    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if not user:
            return {"ok": False, "error": "user not found"}
        active = get_active_delivery(db, user)
        if not active:
            return {"ok": True, "active": None}
        return {"ok": True, "active": get_delivery_detail(db, active.id, user)}
    finally:
        db.close()


@guarded
def nearby_delivery_jobs_tool(limit: int = 5) -> dict[str, Any]:
    """List nearby available delivery jobs for an online rider."""
    uid, role, _sub = _get_session_identity()
    if role != "rider" or uid is None:
        return {"ok": False, "error": "rider role required"}
    from marketplace.database import SessionLocal
    from marketplace.models import User
    from marketplace.dispatch_service import list_available_jobs

    db = SessionLocal()
    try:
        user = db.get(User, uid)
        if not user:
            return {"ok": False, "error": "user not found"}
        jobs = list_available_jobs(db, user, limit=limit)
        result: dict[str, Any] = {"ok": True, "jobs": jobs}
        if not jobs:
            hint = _nearby_jobs_hint(db, user)
            if hint:
                result["hint"] = hint
                result["message"] = {
                    "offline": "Go Online on the Jobs tab to see nearby delivery jobs.",
                    "no_gps": "Share your location on the Jobs tab so nearby jobs can be matched.",
                    "has_active_job": "Finish your current delivery before accepting another job.",
                    "none_nearby": "No delivery jobs nearby right now — stay online and check again soon.",
                }.get(hint, "No jobs available.")
        return result
    finally:
        db.close()
