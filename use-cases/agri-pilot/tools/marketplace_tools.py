"""Marketplace tools for chat (Phase 17).

All tools are session-bound and guarded. They read identity from
ToolContext.get().session (marketplace_user_id) — never from LLM-provided IDs.
Farmer tools require farmer role + active subscription (farmer-only gate);
buyer reads are JWT-only, buyer connect is JWT-only per 2026-08-25 revision.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Optional

from agentkernel.core.tool import ToolContext

from tools.tool_guard import guarded


def _get_session_identity() -> tuple[Optional[int], Optional[str], Optional[str]]:
    """Return (user_id, role, subscription_status) from session KV."""
    try:
        session = ToolContext.get().session
    except Exception:  # noqa: BLE001 - no active tool context
        return None, None, None
    # Canonical mobile / unified channel session: agri:user:{id}
    try:
        from marketplace.session_identity import parse_canonical_session_id, seed_marketplace_session_by_id

        sid = getattr(session, "id", None) or getattr(session, "_id", None)
        uid_from_session = parse_canonical_session_id(str(sid) if sid is not None else None)
        if uid_from_session is not None and not session.get("marketplace_user_id"):
            from marketplace.database import SessionLocal
            from marketplace.models import User

            db = SessionLocal()
            try:
                u = db.get(User, uid_from_session)
                if u:
                    seed_marketplace_session_by_id(session, u.id, u.role, u.subscription_status)
                    return u.id, u.role, u.subscription_status
            finally:
                db.close()
    except Exception:
        pass
    # Support dev helper AK_MARKETPLACE__DEV_USER_ID injection (seeded before run)
    dev_id = os.environ.get("AK_MARKETPLACE__DEV_USER_ID")
    if dev_id and dev_id.strip().isdigit():
        # If session has no user_id but dev helper set, inject it lazily for demo.py
        if not session.get("marketplace_user_id"):
            try:
                from marketplace.database import SessionLocal
                from marketplace.models import User

                dev_uid = int(dev_id.strip())
                db = SessionLocal()
                try:
                    u = db.get(User, dev_uid)
                    if u:
                        session.set("marketplace_user_id", u.id)
                        session.set("marketplace_role", u.role)
                        session.set("marketplace_subscription_status", u.subscription_status)
                finally:
                    db.close()
            except Exception:
                pass
    uid = session.get("marketplace_user_id")
    role = session.get("marketplace_role")
    sub = session.get("marketplace_subscription_status")
    # Fallback: if only id set, load role/sub from DB lazily
    if uid is not None and (role is None or sub is None):
        try:
            from marketplace.database import SessionLocal
            from marketplace.models import User

            db = SessionLocal()
            try:
                u = db.get(User, int(uid))
                if u:
                    role = u.role if role is None else role
                    sub = u.subscription_status if sub is None else sub
                    session.set("marketplace_role", role)
                    session.set("marketplace_subscription_status", sub)
            finally:
                db.close()
        except Exception:
            pass
    # Telegram fallback: session.id may still be chat_id before unified handler migration
    if uid is None:
        try:
            sid = getattr(session, "id", None) or getattr(session, "_id", None)
            if sid is not None:
                from sqlalchemy import select

                from marketplace.database import SessionLocal
                from marketplace.models import User

                db = SessionLocal()
                try:
                    u = db.scalars(select(User).where(User.telegram_chat_id == int(sid))).first()
                    if u and u.role == "farmer" and u.subscription_status == "active":
                        session.set("marketplace_user_id", u.id)
                        session.set("marketplace_role", u.role)
                        session.set("marketplace_subscription_status", u.subscription_status)
                        return u.id, u.role, u.subscription_status
                finally:
                    db.close()
        except Exception:
            pass
    # WhatsApp fallback: session.id is from_number (wa_id) when KV not set
    if uid is None:
        try:
            sid = getattr(session, "id", None) or getattr(session, "_id", None)
            if sid:
                raw = str(sid).strip()
                if raw:
                    if not raw.startswith("+"):
                        raw = "+" + raw.lstrip("+")
                    try:
                        from sqlalchemy import select

                        from marketplace.auth import normalize_phone
                        from marketplace.database import SessionLocal
                        from marketplace.models import User

                        norm = normalize_phone(raw)
                        db = SessionLocal()
                        try:
                            u = db.scalars(select(User).where(User.phone_number == norm)).first()
                            if u and u.role == "farmer" and u.subscription_status == "active":
                                session.set("marketplace_user_id", u.id)
                                session.set("marketplace_role", u.role)
                                session.set("marketplace_subscription_status", u.subscription_status)
                                return u.id, u.role, u.subscription_status
                        finally:
                            db.close()
                    except Exception:
                        pass
        except Exception:
            pass
    try:
        uid_int = int(uid) if uid is not None else None
    except Exception:
        uid_int = None
    # Re-read after possible WhatsApp injection
    if uid_int is None:
        try:
            uid2 = session.get("marketplace_user_id")
            if uid2 is not None:
                uid_int = int(uid2)
                role = session.get("marketplace_role")
                sub = session.get("marketplace_subscription_status")
                return uid_int, role, sub
        except Exception:
            pass
    return uid_int, role, sub


def _get_db_user(user_id: int):
    """Load User row for tool auth checks."""
    from marketplace.database import SessionLocal
    from marketplace.models import User

    db = SessionLocal()
    try:
        u = db.get(User, user_id)
        # Return detached copy of needed fields; keep db open for service calls? Caller will open its own.
        return u
    finally:
        db.close()


@guarded
def create_listing_tool(
    crop: str,
    quantity_kg: float,
    price_per_kg: Optional[float] = None,
    harvest_date: Optional[str] = None,
) -> dict[str, Any]:
    """Call this to create a sell listing when the farmer states they have a quantity of a crop to sell. The listing is stored durably and appears in buyer browse/match. Does not set buyer contacts; contact is via separate GET .../contact after accepted."""
    uid, role, sub = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in on the app to create listings."}
    if role != "farmer":
        return {"error": "role", "message": "Only farmers can create sell listings."}
    # Farmer-only subscription gate (buyer has no subscription per revision)
    if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1" and sub != "active":
        return {"error": "subscription", "message": "Your subscription is not active — renew to sell via chat."}

    # Validation mirrors ListingCreate
    if not crop or not crop.strip():
        return {"error": "validation", "message": "crop must be non-empty"}
    try:
        qty = float(quantity_kg)
        if qty <= 0:
            return {"error": "validation", "message": "quantity_kg must be > 0"}
    except Exception:
        return {"error": "validation", "message": "quantity_kg must be a number > 0"}
    if price_per_kg is not None:
        try:
            pp = float(price_per_kg)
            if pp < 0:
                return {"error": "validation", "message": "price_per_kg must be >= 0"}
            price_per_kg = pp
        except Exception:
            return {"error": "validation", "message": "price_per_kg must be a number >= 0"}
    harvest_date_obj = None
    if harvest_date is not None:
        hd = str(harvest_date).strip()
        if hd:
            try:
                harvest_date_obj = datetime.strptime(hd, "%Y-%m-%d").date()
            except Exception:
                return {"error": "validation", "message": "harvest_date must be YYYY-MM-DD or null"}
        else:
            harvest_date_obj = None

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import create_listing

        db = SessionLocal()
        try:
            listing = create_listing(
                db,
                farmer_id=uid,
                crop=crop,
                quantity_kg=qty,
                price_per_kg=price_per_kg,
                harvest_date=harvest_date_obj,
            )
            status_val = getattr(listing.status, "value", listing.status)
            return {
                "listing_id": listing.id,
                "crop": listing.crop,
                "quantity_kg": listing.quantity_kg,
                "price_per_kg": listing.price_per_kg,
                "harvest_date": str(listing.harvest_date) if listing.harvest_date else None,
                "status": str(status_val),
            }
        finally:
            db.close()
    except ValueError as exc:
        return {"error": "validation", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}


@guarded
def list_my_listings_tool(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List the farmer's own sell listings. Shows only your listings, with status and quantities. Requires farmer login."""
    uid, role, sub = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in to view your listings."}
    if role != "farmer":
        return {"error": "role", "message": "Only farmers have own listings."}
    if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1" and sub != "active":
        return {
            "error": "subscription",
            "message": "Your subscription is not active — renew to view listings via chat.",
        }
    if status is not None and status not in {"active", "sold", "expired", "cancelled"}:
        return {"error": "validation", "message": "status must be one of active|sold|expired|cancelled"}

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import count_own_listings, list_own_listings

        db = SessionLocal()
        try:
            # Clamp via service helper
            items = list_own_listings(db, farmer_id=uid, status=status, limit=int(limit), offset=int(offset))
            total = count_own_listings(db, farmer_id=uid, status=status)
            return {
                "items": [
                    {
                        "id": r.id,
                        "crop": r.crop,
                        "quantity_kg": r.quantity_kg,
                        "price_per_kg": r.price_per_kg,
                        "harvest_date": str(r.harvest_date) if r.harvest_date else None,
                        "status": str(getattr(r.status, "value", r.status)),
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in items
                ],
                "total": total,
                "limit": int(limit),
                "offset": int(offset),
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}


@guarded
def delete_listing_tool(listing_id: int) -> dict[str, Any]:
    """Delete one of your sell listings by its ID. Requires farmer login and that you own the listing. Does not affect other farmers' listings."""
    uid, role, sub = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in to delete listings."}
    if role != "farmer":
        return {"error": "role", "message": "Only farmers can delete listings."}
    if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") != "1" and sub != "active":
        return {
            "error": "subscription",
            "message": "Your subscription is not active — renew to manage listings via chat.",
        }
    try:
        lid = int(listing_id)
    except Exception:
        return {"error": "validation", "message": "listing_id must be an integer"}

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import delete_listing

        db = SessionLocal()
        try:
            ok = delete_listing(db, farmer_id=uid, listing_id=lid)
            if not ok:
                return {"error": "not found", "message": "listing not found"}
            return {"deleted": True, "listing_id": lid}
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}


@guarded
def browse_listings_tool(
    crop: Optional[str] = None,
    district: Optional[str] = None,
    min_qty: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Browse active sell listings with filters. Calls the same browse service as GET /api/buyer/listings. Does not return phone numbers; price is whatever the farmer set (does not set prices). Requires login."""
    uid, role, _ = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in to browse listings."}
    # Farmer and buyer can read (buyer-primary, farmer allowed)
    if role not in {"buyer", "farmer"}:
        return {"error": "role", "message": "Login as buyer or farmer to browse."}
    # No subscription gate for reads (buyer has no subscription)
    # Validate limit
    try:
        lim = int(limit)
        lim = max(1, min(50, lim))
    except Exception:
        lim = 10
    # Validate filters
    if min_qty is not None:
        try:
            mq = float(min_qty)
            if mq <= 0:
                return {"error": "validation", "message": "min_qty must be > 0"}
            min_qty = mq
        except Exception:
            return {"error": "validation", "message": "min_qty must be a number > 0"}
    if max_price is not None:
        try:
            mp = float(max_price)
            if mp < 0:
                return {"error": "validation", "message": "max_price must be >= 0"}
            max_price = mp
        except Exception:
            return {"error": "validation", "message": "max_price must be a number >= 0"}

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import browse_listings, count_browse_listings

        db = SessionLocal()
        try:
            items = browse_listings(
                db, crop=crop, district=district, min_qty=min_qty, max_price=max_price, limit=lim, offset=0
            )
            total = count_browse_listings(db, crop=crop, district=district, min_qty=min_qty, max_price=max_price)
            return {
                "items": [
                    {
                        "id": r.id,
                        "crop": r.crop,
                        "quantity_kg": r.quantity_kg,
                        "price_per_kg": r.price_per_kg,
                        "harvest_date": str(r.harvest_date) if r.harvest_date else None,
                        "status": str(getattr(r.status, "value", r.status)),
                        "district": None,
                        "created_at": r.created_at.isoformat(),
                        "farmer_id": r.farmer_id,
                    }
                    for r in items
                ],
                "count": len(items),
                "total": total,
                "limit": lim,
            }
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}


@guarded
def match_listings_tool(
    crop: str,
    district: Optional[str] = None,
    quantity_kg: Optional[float] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Ranked suggestions for a desired crop/quantity. Implements same rule as GET /api/buyer/match: exact district=2, same region via data/districts.json=1 else 0, then recency. Does not set prices; does not expose phones. Requires login."""
    uid, role, _ = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in to use matching."}
    if role not in {"buyer", "farmer"}:
        return {"error": "role", "message": "Login as buyer or farmer to use matching."}
    if not crop or not crop.strip():
        return {"error": "validation", "message": "crop is required"}
    try:
        lim = int(limit)
        lim = max(1, min(50, lim))
    except Exception:
        lim = 10
    if quantity_kg is not None:
        try:
            qkg = float(quantity_kg)
            if qkg <= 0:
                return {"error": "validation", "message": "quantity_kg must be > 0"}
            quantity_kg = qkg
        except Exception:
            return {"error": "validation", "message": "quantity_kg must be a number > 0"}

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import match_listings

        db = SessionLocal()
        try:
            results = match_listings(db, crop=crop, district=district, quantity_kg=quantity_kg, limit=lim)
            return {
                "items": [
                    {
                        "listing": {
                            "id": r["listing"].id,
                            "crop": r["listing"].crop,
                            "quantity_kg": r["listing"].quantity_kg,
                            "price_per_kg": r["listing"].price_per_kg,
                            "harvest_date": str(r["listing"].harvest_date) if r["listing"].harvest_date else None,
                            "status": str(getattr(r["listing"].status, "value", r["listing"].status)),
                            "created_at": r["listing"].created_at.isoformat(),
                            "farmer_id": r["listing"].farmer_id,
                        },
                        "score": r["score"],
                        "reason": r["reason"],
                    }
                    for r in results
                ],
                "query": {"crop": crop, "district": district, "quantity_kg": quantity_kg},
            }
        finally:
            db.close()
    except ValueError as exc:
        return {"error": "validation", "message": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}


@guarded
def connect_to_listing_tool(listing_id: int, message: Optional[str] = None) -> dict[str, Any]:
    """Express interest in a listing. Creates a pending connection (same service as POST /api/buyer/listings/{id}/connect). Buyer-only write; does not expose farmer phone (use separate GET .../contact after accepted). Does not create sell listings."""
    uid, role, _ = _get_session_identity()
    if uid is None:
        return {"error": "not authenticated", "message": "Please log in to connect to listings."}
    if role != "buyer":
        return {
            "error": "role",
            "message": "Only buyers can connect to listings. Create a buyer account or log in as a buyer.",
        }
    # Buyer has no subscription gate per 2026-08-25
    try:
        lid = int(listing_id)
    except Exception:
        return {"error": "validation", "message": "listing_id must be an integer"}
    if message is not None and len(message) > 500:
        return {"error": "validation", "message": "message must be <= 500 characters"}

    try:
        from marketplace.database import SessionLocal
        from marketplace.service import create_connection_request

        db = SessionLocal()
        try:
            cr = create_connection_request(db, buyer_id=uid, listing_id=lid, message=message)
            # Best-effort notify farmer (never blocks success)
            try:
                from marketplace.models import Listing
                from marketplace.notifications import notify_farmer_of_request

                listing = db.get(Listing, lid)
                if listing:
                    notify_farmer_of_request(listing.farmer_id, lid, cr.id)
            except Exception:
                pass
            return {
                "connection_id": cr.id,
                "status": str(getattr(cr.status, "value", cr.status)),
                "listing_id": cr.listing_id,
            }
        finally:
            db.close()
    except LookupError as exc:
        return {"error": "not found", "message": str(exc)}
    except PermissionError as exc:
        return {"error": "role", "message": str(exc)}
    except ValueError as exc:
        msg = str(exc)
        if "already requested" in msg:
            return {"error": "duplicate", "message": "already requested"}
        return {"error": "validation", "message": msg}
    except Exception as exc:  # noqa: BLE001
        return {"error": "internal", "message": str(exc)}
