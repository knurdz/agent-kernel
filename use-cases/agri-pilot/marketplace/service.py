"""Shared service layer for marketplace (Phase 15 / App.md:56).

This is the **single** write path used by both REST handlers and the future
chat tool (Phase 17). Callers must not duplicate crop normalization / validation.
"""

from __future__ import annotations

import json
import pathlib
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from marketplace.models import BuyerProfile, ConnectionRequest, FarmerProfile, Listing, User, UserRole


# ---------- helpers ----------
def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
    return db.scalars(select(User).where(User.phone_number == phone_number)).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def create_user_with_profile(
    db: Session,
    *,
    role: str,
    phone_number: str,
    password_hash: str,
    name: str,
    subscription_status: str = "active",
    location: Optional[str] = None,
    district: Optional[str] = None,
    preferred_language: Optional[str] = None,
    business_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
) -> User:
    user = User(
        phone_number=phone_number,
        role=role,
        password_hash=password_hash,
        name=name,
        subscription_status=subscription_status,
    )
    db.add(user)
    db.flush()  # populate user.id
    if role == "farmer":
        db.add(
            FarmerProfile(
                user_id=user.id,
                location=location,
                district=district,
                preferred_language=preferred_language,
                contact_phone=contact_phone,
            )
        )
    else:
        db.add(BuyerProfile(user_id=user.id, business_name=business_name, location=location, district=district))
    db.commit()
    db.refresh(user)
    return user


# ---------- listings ----------
def create_listing(
    db: Session,
    *,
    farmer_id: int,
    crop: str,
    quantity_kg: float,
    price_per_kg: Optional[float] = None,
    harvest_date: Optional[date] = None,
) -> Listing:
    farmer = db.get(User, farmer_id)
    if not farmer or farmer.role != UserRole.farmer.value:
        raise ValueError("farmer not found or not a farmer")

    if not crop or not crop.strip():
        raise ValueError("crop must be non-empty")
    if quantity_kg is None or float(quantity_kg) <= 0:
        raise ValueError("quantity_kg must be > 0")
    if price_per_kg is not None and float(price_per_kg) < 0:
        raise ValueError("price_per_kg must be >= 0")

    listing = Listing(
        farmer_id=farmer_id,
        crop=crop.strip().lower(),
        quantity_kg=float(quantity_kg),
        price_per_kg=float(price_per_kg) if price_per_kg is not None else None,
        harvest_date=harvest_date,
        status="active",
    )
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return listing


def list_own_listings(
    db: Session, farmer_id: int, status: Optional[str] = None, limit: int = 20, offset: int = 0
) -> list[Listing]:
    q = select(Listing).where(Listing.farmer_id == farmer_id)
    if status:
        q = q.where(Listing.status == status)
    q = q.order_by(Listing.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


def count_own_listings(db: Session, farmer_id: int, status: Optional[str] = None) -> int:
    q = select(func.count()).select_from(Listing).where(Listing.farmer_id == farmer_id)
    if status:
        q = q.where(Listing.status == status)
    return int(db.scalar(q) or 0)


def get_listing(db: Session, listing_id: int) -> Optional[Listing]:
    return db.get(Listing, listing_id)


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "active": {"sold", "expired", "cancelled"},
    "cancelled": {"active"},
    "expired": {"active"},
    # sold is terminal
}


def update_listing(db: Session, farmer_id: int, listing_id: int, patch: dict) -> Optional[Listing]:
    listing = db.get(Listing, listing_id)
    if not listing or listing.farmer_id != farmer_id:
        return None

    # Validate status transition before applying.
    new_status = patch.get("status")
    if new_status and new_status != listing.status:
        if listing.status == "sold":
            raise ValueError("sold listings cannot be reactivated")
        allowed = _ALLOWED_TRANSITIONS.get(listing.status, set())
        if new_status not in allowed:
            raise ValueError(f"invalid status transition {listing.status} -> {new_status}")

    for key in ("crop", "quantity_kg", "price_per_kg", "harvest_date", "status"):
        if key in patch and patch[key] is not None:
            val = patch[key]
            if key == "crop":
                val = str(val).strip().lower()
                if not val:
                    raise ValueError("crop must be non-empty")
            elif key == "quantity_kg":
                if float(val) <= 0:
                    raise ValueError("quantity_kg must be > 0")
                val = float(val)
            elif key == "price_per_kg":
                if val is not None and float(val) < 0:
                    raise ValueError("price_per_kg must be >= 0")
                val = float(val) if val is not None else None
            setattr(listing, key, val)
        elif key in patch and patch[key] is None and key in ("price_per_kg", "harvest_date"):
            setattr(listing, key, None)

    listing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(listing)
    return listing


def delete_listing(db: Session, farmer_id: int, listing_id: int) -> bool:
    listing = db.get(Listing, listing_id)
    if not listing or listing.farmer_id != farmer_id:
        return False
    db.delete(listing)
    db.commit()
    return True


# ---------- buyer browse / discovery (Phase 16.1) ----------
def _clamp_limit(limit: int) -> int:
    try:
        v = int(limit)
    except Exception:
        v = 20
    return max(1, min(50, v))


def _browse_base_query(
    db: Session,
    *,
    crop: Optional[str] = None,
    district: Optional[str] = None,
    min_qty: Optional[float] = None,
    max_price: Optional[float] = None,
):
    """Build base query for active listings with shared filters."""
    q = select(Listing).where(Listing.status == "active")
    if crop is not None:
        c = crop.strip().lower()
        if c:
            q = q.where(Listing.crop == c)
    if district is not None:
        d = district.strip()
        if d:
            # Join farmer_profiles for district filter (case-insensitive exact)
            q = q.join(FarmerProfile, FarmerProfile.user_id == Listing.farmer_id).where(
                func.lower(FarmerProfile.district) == d.lower()
            )
    if min_qty is not None:
        q = q.where(Listing.quantity_kg >= float(min_qty))
    if max_price is not None:
        q = q.where(Listing.price_per_kg.is_not(None)).where(Listing.price_per_kg <= float(max_price))
        # spec also requires price_per_kg >=0 but filtered listings already satisfy >=0 via check
    return q


def browse_listings(
    db: Session,
    *,
    crop: Optional[str] = None,
    district: Optional[str] = None,
    min_qty: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Listing]:
    limit = _clamp_limit(limit)
    offset = max(0, int(offset))
    q = _browse_base_query(db, crop=crop, district=district, min_qty=min_qty, max_price=max_price)
    q = q.order_by(Listing.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


def count_browse_listings(
    db: Session,
    *,
    crop: Optional[str] = None,
    district: Optional[str] = None,
    min_qty: Optional[float] = None,
    max_price: Optional[float] = None,
) -> int:
    q = _browse_base_query(db, crop=crop, district=district, min_qty=min_qty, max_price=max_price)
    # Convert to count query: select count(*) from (base)
    # Use subquery approach via func.count on Listing.id
    # We need to redo without order/limit
    count_q = select(func.count()).select_from(q.subquery())
    return int(db.scalar(count_q) or 0)


def get_active_listing(db: Session, listing_id: int) -> Optional[Listing]:
    listing = db.get(Listing, listing_id)
    if not listing or listing.status != "active":
        return None
    return listing


# ---------- matching (Phase 16.2) ----------
_DISTRICT_REGION: dict[str, str] = {}


def _load_districts() -> dict[str, str]:
    global _DISTRICT_REGION
    if _DISTRICT_REGION:
        return _DISTRICT_REGION
    # Try multiple candidate paths (project root vs marketplace package)
    candidates = [
        pathlib.Path("data/districts.json"),
        pathlib.Path(__file__).resolve().parents[1] / "data" / "districts.json",
    ]
    for p in candidates:
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                # Normalize keys to lower for case-insensitive lookup but preserve region case
                _DISTRICT_REGION = {str(k).strip(): str(v).strip() for k, v in data.items() if k and v}
                break
        except Exception:
            continue
    return _DISTRICT_REGION


def _district_score(listing_district: Optional[str], query_district: Optional[str]) -> tuple[int, str]:
    """Return (score, reason) for ranking."""
    if not query_district or not query_district.strip():
        return 0, "other district"
    if not listing_district or not listing_district.strip():
        return 0, "other district"
    q = query_district.strip().lower()
    ld = listing_district.strip().lower()
    if ld == q:
        return 2, "exact district"
    # Same region via districts.json
    mapping = _load_districts()
    # Find region for listing and query (case-sensitive keys as stored)
    # Do case-insensitive lookup in mapping
    q_region = None
    l_region = None
    for k, v in mapping.items():
        if k.lower() == q:
            q_region = v
        if k.lower() == ld:
            l_region = v
    if q_region and l_region and q_region == l_region:
        return 1, f"same region ({q_region})"
    return 0, "other district"


def match_listings(
    db: Session,
    *,
    crop: str,
    district: Optional[str] = None,
    quantity_kg: Optional[float] = None,
    limit: int = 20,
) -> list[dict]:
    if not crop or not crop.strip():
        raise ValueError("crop is required")
    crop_norm = crop.strip().lower()
    limit = _clamp_limit(limit)

    q = select(Listing).where(Listing.status == "active").where(Listing.crop == crop_norm)
    if quantity_kg is not None:
        q = q.where(Listing.quantity_kg >= float(quantity_kg))
    # No order yet; ranking done in python after scoring
    candidates = list(db.scalars(q).all())

    # Need farmer district for each listing
    scored: list[tuple[int, datetime, Listing, str]] = []
    for lst in candidates:
        # Use relationship or direct query for district
        fp = db.get(FarmerProfile, lst.farmer_id)
        listing_district = fp.district if fp else None
        score, reason = _district_score(listing_district, district)
        # store tuple for sorting: (-score, -created_at)
        scored.append((score, lst.created_at, lst, reason))

    # Sort: exact (2) first, region (1) second, then most recent
    scored.sort(key=lambda x: (-x[0], -x[1].timestamp()))

    result: list[dict] = []
    for score, _, lst, reason in scored[:limit]:
        result.append({"listing": lst, "score": score, "reason": reason})
    return result


# ---------- connections (Phase 16.3) ----------
_ALLOWED_CONNECTION_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"accepted", "declined"},
    "accepted": {"completed"},
    # declined and completed are terminal
}


def create_connection_request(
    db: Session,
    *,
    buyer_id: int,
    listing_id: int,
    message: Optional[str] = None,
) -> ConnectionRequest:
    listing = db.get(Listing, listing_id)
    if not listing or listing.status != "active":
        raise LookupError("listing not found")
    buyer = db.get(User, buyer_id)
    if not buyer or buyer.role != UserRole.buyer.value:
        raise PermissionError("buyer role required")
    if buyer_id == listing.farmer_id:
        raise ValueError("cannot connect to own listing")
    if message is not None and len(message) > 500:
        raise ValueError("message too long (max 500)")

    # No existing pending for same (listing_id, buyer_id)
    existing = db.scalars(
        select(ConnectionRequest).where(
            ConnectionRequest.listing_id == listing_id,
            ConnectionRequest.buyer_id == buyer_id,
            ConnectionRequest.status == "pending",
        )
    ).first()
    if existing:
        raise ValueError("already requested")

    # seam: Phase 18+ transactions/deliveries attach when status becomes completed
    cr = ConnectionRequest(
        listing_id=listing_id,
        buyer_id=buyer_id,
        status="pending",
        message=message,
    )
    db.add(cr)
    db.commit()
    db.refresh(cr)
    return cr


def list_buyer_connections(db: Session, buyer_id: int) -> list[ConnectionRequest]:
    q = (
        select(ConnectionRequest)
        .where(ConnectionRequest.buyer_id == buyer_id)
        .order_by(ConnectionRequest.created_at.desc())
    )
    return list(db.scalars(q).all())


def list_farmer_connections(db: Session, farmer_id: int) -> list[ConnectionRequest]:
    # Join listing to filter where listing.farmer_id == farmer_id
    q = (
        select(ConnectionRequest)
        .join(Listing, Listing.id == ConnectionRequest.listing_id)
        .where(Listing.farmer_id == farmer_id)
        .order_by(ConnectionRequest.created_at.desc())
    )
    return list(db.scalars(q).all())


def update_connection_status(
    db: Session,
    *,
    farmer_id: int,
    connection_id: int,
    new_status: str,
) -> Optional[ConnectionRequest]:
    if new_status not in {"accepted", "declined", "completed"}:
        raise ValueError("invalid status")
    conn = db.get(ConnectionRequest, connection_id)
    if not conn:
        return None
    listing = db.get(Listing, conn.listing_id)
    if not listing or listing.farmer_id != farmer_id:
        return None
    current = conn.status
    if current in {"declined", "completed"}:
        raise ValueError("already terminal")
    allowed = _ALLOWED_CONNECTION_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(f"invalid status transition {current} -> {new_status}")
    # seam: Phase 18+ transactions/deliveries attach here; do not add payments table yet
    # when new_status == "completed", future transactions attach to this connection
    conn.status = new_status
    conn.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(conn)
    return conn


def get_connection_contact(
    db: Session,
    *,
    connection_id: int,
    requester_id: int,
    requester_role: str,
) -> tuple[ConnectionRequest, Listing, str]:
    """Return (connection, listing, phone) for gated contact reveal.

    Raises LookupError if not found / not owned, ValueError if not yet accepted.
    """
    conn = db.get(ConnectionRequest, connection_id)
    if not conn:
        raise LookupError("connection not found")
    listing = db.get(Listing, conn.listing_id)
    if not listing:
        raise LookupError("listing not found")

    if requester_role == "buyer":
        if conn.buyer_id != requester_id:
            raise LookupError("connection not found")
        # buyer retrieving farmer contact
        if conn.status not in {"accepted", "completed"}:
            raise ValueError("contact not available until accepted")
        farmer = db.get(User, listing.farmer_id)
        if not farmer:
            raise LookupError("farmer not found")
        fp = db.get(FarmerProfile, farmer.id)
        contact = None
        if fp and fp.contact_phone and fp.contact_phone.strip():
            contact = fp.contact_phone.strip()
        else:
            contact = farmer.phone_number
        return conn, listing, contact
    elif requester_role == "farmer":
        if listing.farmer_id != requester_id:
            raise LookupError("connection not found")
        if conn.status not in {"accepted", "completed"}:
            raise ValueError("contact not available until accepted")
        buyer = db.get(User, conn.buyer_id)
        if not buyer:
            raise LookupError("buyer not found")
        return conn, listing, buyer.phone_number
    else:
        raise PermissionError("role not allowed")
