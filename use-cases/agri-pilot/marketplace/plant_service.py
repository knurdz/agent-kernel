"""Service layer for plant tracking and crop insights."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from marketplace.models import Listing, Plant, PlantObservation, User, UserRole
from marketplace.plant_media import save_plant_photo

CONFIDENCE_THRESHOLD = 0.7


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_crop(crop: str) -> str:
    c = crop.strip().lower()
    if not c:
        raise ValueError("crop must be non-empty")
    return c


def _link_plant_listing(db: Session, plant: Plant, listing: Listing) -> None:
    plant.listing_id = listing.id
    listing.plant_id = plant.id
    plant.updated_at = _utcnow()
    listing.updated_at = _utcnow()


def create_plant(
    db: Session,
    *,
    farmer_id: int,
    crop: str,
    name: Optional[str] = None,
    planted_on: Optional[date] = None,
    listing_id: Optional[int] = None,
) -> Plant:
    farmer = db.get(User, farmer_id)
    if not farmer or farmer.role != UserRole.farmer.value:
        raise ValueError("farmer not found or not a farmer")

    crop_norm = _normalize_crop(crop)
    plant = Plant(
        farmer_id=farmer_id,
        crop=crop_norm,
        name=(name or crop_norm).strip() or crop_norm,
        planted_on=planted_on,
    )
    db.add(plant)
    db.flush()

    if listing_id is not None:
        listing = db.get(Listing, listing_id)
        if not listing or listing.farmer_id != farmer_id:
            raise ValueError("listing not found")
        if listing.plant_id is not None:
            raise ValueError("listing already linked to a plant")
        existing = db.scalars(select(Plant).where(Plant.listing_id == listing_id)).first()
        if existing:
            raise ValueError("listing already linked to a plant")
        _link_plant_listing(db, plant, listing)

    db.commit()
    db.refresh(plant)
    return plant


def list_plants(db: Session, farmer_id: int, limit: int = 50, offset: int = 0) -> list[Plant]:
    q = select(Plant).where(Plant.farmer_id == farmer_id).order_by(Plant.updated_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(q).all())


def count_plants(db: Session, farmer_id: int) -> int:
    q = select(func.count()).select_from(Plant).where(Plant.farmer_id == farmer_id)
    return int(db.scalar(q) or 0)


def get_plant(db: Session, farmer_id: int, plant_id: int) -> Optional[Plant]:
    plant = db.get(Plant, plant_id)
    if not plant or plant.farmer_id != farmer_id:
        return None
    return plant


def import_plant_from_listing(db: Session, farmer_id: int, listing_id: int) -> Plant:
    listing = db.get(Listing, listing_id)
    if not listing or listing.farmer_id != farmer_id:
        raise LookupError("listing not found")
    if listing.plant_id is not None:
        raise ValueError("listing already linked to a plant")
    existing = db.scalars(select(Plant).where(Plant.listing_id == listing_id)).first()
    if existing:
        raise ValueError("listing already linked to a plant")

    plant = Plant(
        farmer_id=farmer_id,
        crop=listing.crop,
        name=listing.crop,
    )
    db.add(plant)
    db.flush()
    _link_plant_listing(db, plant, listing)
    db.commit()
    db.refresh(plant)
    return plant


def append_observation(
    db: Session,
    *,
    farmer_id: int,
    plant_id: int,
    photo_file,
    filename: str,
    analysis: dict[str, Any],
    source: str = "tracking",
) -> PlantObservation:
    plant = get_plant(db, farmer_id, plant_id)
    if not plant:
        raise LookupError("plant not found")

    rel_path = save_plant_photo(farmer_id, plant_id, photo_file, filename)
    obs = PlantObservation(
        plant_id=plant_id,
        photo_path=rel_path,
        captured_at=_utcnow(),
        quality_ok=bool(analysis.get("quality_ok")),
        quality_reason=analysis.get("quality_reason"),
        top_label=analysis.get("top_label"),
        top_confidence=analysis.get("top_confidence"),
        predictions=analysis.get("predictions"),
        advice_summary=analysis.get("advice_summary"),
        source=source,
    )
    db.add(obs)
    plant.updated_at = _utcnow()
    db.commit()
    db.refresh(obs)
    return obs


def list_observations(db: Session, plant_id: int) -> list[PlantObservation]:
    q = select(PlantObservation).where(PlantObservation.plant_id == plant_id).order_by(PlantObservation.captured_at.asc())
    return list(db.scalars(q).all())


def _severity_rank(label: str | None) -> int:
    if not label:
        return 0
    lower = label.lower()
    if "healthy" in lower:
        return 0
    if any(x in lower for x in ("mild", "early", "spot")):
        return 1
    if any(x in lower for x in ("moderate", "blight", "rust")):
        return 2
    return 3


def _health_series(observations: list[PlantObservation]) -> list[dict[str, Any]]:
    series: list[dict[str, Any]] = []
    for o in observations:
        if not o.quality_ok or not o.top_label or o.top_confidence is None:
            continue
        if o.top_confidence < CONFIDENCE_THRESHOLD:
            continue
        series.append(
            {
                "date": o.captured_at.date().isoformat(),
                "label": o.top_label,
                "confidence": o.top_confidence,
                "severity": _severity_rank(o.top_label),
            }
        )
    return series


def compute_trend(observations: list[PlantObservation]) -> str:
    confident = [
        o
        for o in observations
        if o.quality_ok and o.top_label and o.top_confidence is not None and o.top_confidence >= CONFIDENCE_THRESHOLD
    ]
    if len(confident) < 2:
        return "unknown"
    first, last = confident[0], confident[-1]
    first_rank = _severity_rank(first.top_label)
    last_rank = _severity_rank(last.top_label)
    if last_rank < first_rank:
        return "improving"
    if last_rank > first_rank:
        return "worsening"
    return "stable"


def build_plant_insights(plant: Plant, observations: list[PlantObservation]) -> dict[str, Any]:
    from tools.crop_guide import compute_crop_care

    confident = [
        o
        for o in observations
        if o.quality_ok and o.top_label and o.top_confidence is not None and o.top_confidence >= CONFIDENCE_THRESHOLD
    ]
    latest = confident[-1] if confident else None
    timeline = [
        {
            "date": o.captured_at.date().isoformat(),
            "label": o.top_label,
            "confidence": o.top_confidence,
        }
        for o in confident
    ]
    health_series = _health_series(observations)
    crop_care = compute_crop_care(plant.crop, planted_on=plant.planted_on)
    return {
        "crop": plant.crop,
        "observation_count": len(observations),
        "first_observation_date": observations[0].captured_at.date().isoformat() if observations else None,
        "last_observation_date": observations[-1].captured_at.date().isoformat() if observations else None,
        "latest_label": latest.top_label if latest else None,
        "latest_confidence": latest.top_confidence if latest else None,
        "timeline": timeline,
        "health_series": health_series,
        "trend": compute_trend(observations),
        "crop_care": crop_care,
        "growth_progress": crop_care.get("growth_progress") if crop_care else None,
    }


def update_plant(
    db: Session,
    *,
    farmer_id: int,
    plant_id: int,
    name: Optional[str] = None,
    planted_on: Optional[date] = None,
    clear_planted_on: bool = False,
) -> Plant:
    plant = get_plant(db, farmer_id, plant_id)
    if not plant:
        raise LookupError("plant not found")
    if name is not None:
        trimmed = name.strip()
        if trimmed:
            plant.name = trimmed
    if clear_planted_on:
        plant.planted_on = None
    elif planted_on is not None:
        plant.planted_on = planted_on
    plant.updated_at = _utcnow()
    db.commit()
    db.refresh(plant)
    return plant


def get_listing_insights(db: Session, listing_id: int) -> Optional[dict[str, Any]]:
    listing = db.get(Listing, listing_id)
    if not listing or listing.status != "active" or listing.plant_id is None:
        return None
    plant = db.get(Plant, listing.plant_id)
    if not plant:
        return None
    observations = list_observations(db, plant.id)
    if not observations:
        return None
    insights = build_plant_insights(plant, observations)
    insights["listing_id"] = listing.id
    insights["plant_id"] = plant.id
    return insights
