"""Farmer listings router (App.md:51-54) + farmer connections inbox (Phase 16).

Gated by JWT + farmer role + active subscription (owner decision #3).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user, require_active_subscription, require_role
from marketplace.database import get_db
from marketplace.models import Listing, User
from marketplace.schemas import ListingCreate, ListingResponse, ListingUpdate, PaginatedListings
from marketplace.service import (
    count_own_listings,
    create_listing,
    delete_listing,
    get_listing,
    list_own_listings,
    update_listing,
)

router = APIRouter(prefix="/api/farmer", tags=["farmer"])


def _farmer_active(user: User = Depends(get_current_user)) -> User:
    # role + subscription in one dependency
    if user.role != "farmer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="farmer role required")
    # reuse helper logic inline to keep single Depends surface
    import os

    if os.environ.get("AK_MARKETPLACE__SKIP_SUBSCRIPTION_CHECK") == "1":
        return user
    if user.subscription_status != "active":
        detail = "farmer subscription required"
        if user.subscription_status == "expired":
            detail = "farmer subscription expired — please renew"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    return user


@router.post("/listings", response_model=ListingResponse, status_code=status.HTTP_201_CREATED)
def post_listing(payload: ListingCreate, db: Session = Depends(get_db), farmer: User = Depends(_farmer_active)):
    try:
        listing = create_listing(
            db,
            farmer_id=farmer.id,
            crop=payload.crop,
            quantity_kg=payload.quantity_kg,
            price_per_kg=payload.price_per_kg,
            harvest_date=payload.harvest_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return listing


@router.get("/listings", response_model=PaginatedListings)
def get_my_listings(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    if status and status not in ("active", "sold", "expired", "cancelled"):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status")
    items = list_own_listings(db, farmer.id, status=status, limit=limit, offset=offset)
    total = count_own_listings(db, farmer.id, status=status)
    return PaginatedListings(items=items, total=total, limit=limit, offset=offset)


@router.patch("/listings/{listing_id}", response_model=ListingResponse)
def patch_listing(
    listing_id: int,
    payload: ListingUpdate,
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    existing = get_listing(db, listing_id)
    if not existing or existing.farmer_id != farmer.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found")
    patch = payload.model_dump(exclude_unset=True, exclude_none=False)
    # Don't pass None for unset fields; pydantic's exclude_unset already handles it.
    # But explicit None for price/harvest should be passed.
    try:
        updated = update_listing(db, farmer.id, listing_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found")
    return updated


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_listing(listing_id: int, db: Session = Depends(get_db), farmer: User = Depends(_farmer_active)):
    ok = delete_listing(db, farmer.id, listing_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found")
    return None
