"""Read-only delivery/order tools for chat (session-bound, guarded)."""

from __future__ import annotations

from typing import Any, Optional

from agentkernel.core.tool import ToolContext

from tools.marketplace_tools import _get_session_identity
from tools.tool_guard import guarded


@guarded
def my_orders_tool(limit: int = 10) -> dict[str, Any]:
    """List the authenticated user's orders (buyer, farmer, or rider view)."""
    uid, role, _sub = _get_session_identity()
    if uid is None:
        return {"ok": False, "error": "not authenticated — log in via the app"}
    from marketplace.database import SessionLocal
    from marketplace.order_serializers import order_to_response
    from marketplace.order_service import list_buyer_orders, list_farmer_orders
    from marketplace.dispatch_service import list_rider_deliveries

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
            return {
                "ok": True,
                "role": role,
                "deliveries": [
                    {"delivery_id": d.id, "order_id": d.order_id, "status": d.status, "rider_id": d.rider_id}
                    for d in deliveries
                ],
            }
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
        return {"ok": True, "jobs": jobs}
    finally:
        db.close()
