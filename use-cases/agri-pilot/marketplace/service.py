"""Shared service layer for marketplace (Phase 15 / App.md:56).

This is the **single** write path used by both REST handlers and the future
chat tool (Phase 17). Callers must not duplicate crop normalization / validation.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
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
    from sqlalchemy import func

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
