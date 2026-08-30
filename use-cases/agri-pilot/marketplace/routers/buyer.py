"""Buyer discovery, matching and connections (Phase 16)."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from marketplace.auth import get_current_user, require_role
from marketplace.database import get_db
from marketplace.models import Listing
from marketplace.schemas import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionWithListing,
    ContactResponse,
    ListingInsights,
    ListingResponse,
    MatchResponse,
    PaginatedListings,
)
from marketplace.service import (
    browse_listings,
    count_browse_listings,
    create_connection_request,
    get_active_listing,
    get_connection_contact,
    list_buyer_connections,
    match_listings,
)

log = logging.getLogger("agripilot.marketplace.buyer")

router = APIRouter(prefix="/api/buyer", tags=["buyer"])


def _buyer_user(user=Depends(get_current_user)):
    # Buyer role required; no subscription check for buyers (decision 3/4)
    if user.role != "buyer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="buyer role required")
    return user


@router.get("/listings", response_model=PaginatedListings)
def get_listings(
    crop: Optional[str] = Query(default=None),
    district: Optional[str] = Query(default=None),
    min_qty: Optional[float] = Query(default=None, gt=0),
    max_price: Optional[float] = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    # Use guarded service; ensure filters are combined with AND
    items = browse_listings(
        db, crop=crop, district=district, min_qty=min_qty, max_price=max_price, limit=limit, offset=offset
    )
    total = count_browse_listings(db, crop=crop, district=district, min_qty=min_qty, max_price=max_price)
    return PaginatedListings(items=items, total=total, limit=limit, offset=offset)


@router.get("/listings/{listing_id}", response_model=ListingResponse)
def get_listing_detail(
    listing_id: int,
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    listing = get_active_listing(db, listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found")
    return listing


@router.get("/match", response_model=MatchResponse)
def get_match(
    crop: str = Query(..., min_length=1),
    quantity_kg: Optional[float] = Query(default=None, gt=0),
    district: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    try:
        results = match_listings(db, crop=crop, district=district, quantity_kg=quantity_kg, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    items = [{"listing": r["listing"], "score": r["score"], "reason": r["reason"]} for r in results]
    return MatchResponse(items=items, query={"crop": crop, "district": district, "quantity_kg": quantity_kg})


@router.post("/listings/{listing_id}/connect", response_model=ConnectionResponse, status_code=status.HTTP_201_CREATED)
def post_connect(
    listing_id: int,
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    try:
        cr = create_connection_request(db, buyer_id=buyer.id, listing_id=listing_id, message=payload.message)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        msg = str(exc)
        if "already requested" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="already requested") from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc

    # Best-effort notify farmer (never blocks 201)
    try:
        from marketplace.notifications import notify_farmer_of_request

        listing = db.get(Listing, listing_id)
        if listing:
            notify_farmer_of_request(listing.farmer_id, listing_id, cr.id)
    except Exception as exc:  # noqa: BLE001
        log.warning("notify failed for connection %s: %s", cr.id, exc, exc_info=False)

    return cr


@router.get("/connections", response_model=list[ConnectionWithListing])
def get_my_connections(
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    conns = list_buyer_connections(db, buyer.id)
    # Build response with listing embedded; no phone leak
    result = []
    for c in conns:
        listing = db.get(Listing, c.listing_id)
        result.append(
            ConnectionWithListing(
                id=c.id,
                listing_id=c.listing_id,
                buyer_id=c.buyer_id,
                status=c.status,
                message=c.message,
                created_at=c.created_at,
                updated_at=c.updated_at,
                listing=listing,  # type: ignore[arg-type]
            )
        )
    return result


@router.get("/connections/{connection_id}/contact", response_model=ContactResponse)
def get_contact_for_buyer(
    connection_id: int,
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    try:
        conn, listing, phone = get_connection_contact(
            db, connection_id=connection_id, requester_id=buyer.id, requester_role="buyer"
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="connection not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return ContactResponse(
        phone_number=phone,
        listing_id=listing.id,
        connection_id=conn.id,
        status=conn.status,
    )


@router.get("/listings/{listing_id}/insights", response_model=ListingInsights)
def get_listing_insights(
    listing_id: int,
    db: Session = Depends(get_db),
    buyer=Depends(_buyer_user),
):
    from marketplace.plant_service import get_listing_insights as _get_insights

    insights = _get_insights(db, listing_id)
    if not insights:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="insights not available")
    return ListingInsights(**insights)
