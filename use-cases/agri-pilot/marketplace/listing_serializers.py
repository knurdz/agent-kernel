"""Serialize Listing ORM rows into API responses with computed fields."""

from __future__ import annotations

from typing import Literal, Optional

from sqlalchemy.orm import Session

from marketplace.models import FarmerProfile, Listing, User
from marketplace.schemas import ListingResponse

Audience = Literal["farmer", "buyer"]


def _available_kg(listing: Listing) -> float:
    return max(0.0, float(listing.quantity_kg) - float(listing.reserved_quantity_kg or 0))


def _farmer_context(db: Session, listing: Listing) -> tuple[Optional[str], Optional[str]]:
    farmer = db.get(User, listing.farmer_id)
    profile = db.get(FarmerProfile, listing.farmer_id)
    return (
        farmer.name if farmer else None,
        profile.district if profile else None,
    )


def listing_to_response(
    db: Session,
    listing: Listing,
    *,
    audience: Audience = "farmer",
) -> ListingResponse:
    farmer_name, district = _farmer_context(db, listing)
    photo_url = None
    if listing.image_path:
        prefix = "/api/farmer/listings" if audience == "farmer" else "/api/buyer/listings"
        photo_url = f"{prefix}/{listing.id}/photo"

    reserved = float(listing.reserved_quantity_kg or 0)
    return ListingResponse(
        id=listing.id,
        farmer_id=listing.farmer_id,
        crop=listing.crop,
        quantity_kg=float(listing.quantity_kg),
        price_per_kg=float(listing.price_per_kg) if listing.price_per_kg is not None else None,
        harvest_date=listing.harvest_date,
        status=listing.status,
        plant_id=listing.plant_id,
        created_at=listing.created_at,
        updated_at=listing.updated_at,
        category=listing.category,
        description=listing.description,
        view_count=int(listing.view_count or 0),
        photo_url=photo_url,
        available_kg=_available_kg(listing),
        reserved_quantity_kg=reserved if audience == "farmer" else None,
        farmer_name=farmer_name if audience == "buyer" else None,
        district=district if audience == "buyer" else None,
    )


def listings_to_responses(
    db: Session,
    listings: list[Listing],
    *,
    audience: Audience = "farmer",
) -> list[ListingResponse]:
    return [listing_to_response(db, listing, audience=audience) for listing in listings]
