"""Farmer plant tracking and one-time crop scans."""

from __future__ import annotations

import os
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from marketplace.database import get_db
from marketplace.models import Plant, PlantObservation, User
from marketplace.plant_media import resolve_photo_path
from marketplace.plant_service import (
    append_observation,
    build_plant_insights,
    count_plants,
    create_plant,
    get_plant,
    import_plant_from_listing,
    list_observations,
    list_plants,
)
from marketplace.schemas import (
    PaginatedPlants,
    PlantCreate,
    PlantDetail,
    PlantInsights,
    PlantObservationOut,
    PlantSummary,
    PredictionOut,
    ScanResult,
)
from marketplace.routers.farmer import _farmer_active
from tools.vision_tool import analyze_crop_photo

router = APIRouter(prefix="/api/farmer", tags=["farmer-plants"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_upload(upload: UploadFile) -> tuple[bytes, str]:
    data = await upload.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="image too large (max 10 MB)")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty upload")
    filename = upload.filename or "photo.jpg"
    return data, filename


def _analyze_bytes(data: bytes, filename: str, crop: str | None = None) -> dict:
    suffix = os.path.splitext(filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        return analyze_crop_photo(tmp_path, crop=crop)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _scan_result(analysis: dict) -> ScanResult:
    predictions = [
        PredictionOut(label=p["label"], confidence=float(p["confidence"]))
        for p in (analysis.get("predictions") or [])
    ]
    return ScanResult(
        quality_ok=bool(analysis.get("quality_ok")),
        quality_reason=analysis.get("quality_reason"),
        predictions=predictions,
        top_label=analysis.get("top_label"),
        top_confidence=analysis.get("top_confidence"),
        confident=bool(analysis.get("confident")),
        advice_summary=analysis.get("advice_summary"),
    )


def _observation_out(obs: PlantObservation, *, include_photo_url: bool = True) -> PlantObservationOut:
    predictions = None
    if obs.predictions:
        predictions = [PredictionOut(label=p["label"], confidence=float(p["confidence"])) for p in obs.predictions]
    return PlantObservationOut(
        id=obs.id,
        plant_id=obs.plant_id,
        captured_at=obs.captured_at,
        quality_ok=obs.quality_ok,
        quality_reason=obs.quality_reason,
        top_label=obs.top_label,
        top_confidence=obs.top_confidence,
        predictions=predictions,
        advice_summary=obs.advice_summary,
        source=obs.source,
        photo_url=f"/api/farmer/plants/{obs.plant_id}/observations/{obs.id}/photo" if include_photo_url else None,
    )


def _plant_summary(plant: Plant, observations: list[PlantObservation]) -> PlantSummary:
    insights = build_plant_insights(plant, observations)
    return PlantSummary(
        id=plant.id,
        crop=plant.crop,
        name=plant.name,
        planted_on=plant.planted_on,
        listing_id=plant.listing_id,
        observation_count=len(observations),
        latest_label=insights.get("latest_label"),
        trend=insights.get("trend", "unknown"),
        created_at=plant.created_at,
        updated_at=plant.updated_at,
    )


@router.post("/scans", response_model=ScanResult)
async def post_scan(
    image: UploadFile = File(...),
    crop: Optional[str] = Form(default=None),
    farmer: User = Depends(_farmer_active),
):
    data, filename = await _read_upload(image)
    analysis = _analyze_bytes(data, filename, crop=crop)
    return _scan_result(analysis)


@router.get("/plants", response_model=PaginatedPlants)
def get_plants(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    plants = list_plants(db, farmer.id, limit=limit, offset=offset)
    total = count_plants(db, farmer.id)
    items = [_plant_summary(p, list_observations(db, p.id)) for p in plants]
    return PaginatedPlants(items=items, total=total, limit=limit, offset=offset)


@router.post("/plants", response_model=PlantSummary, status_code=status.HTTP_201_CREATED)
def post_plant(
    payload: PlantCreate,
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    try:
        plant = create_plant(
            db,
            farmer_id=farmer.id,
            crop=payload.crop,
            name=payload.name,
            planted_on=payload.planted_on,
            listing_id=payload.listing_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "already linked" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    return _plant_summary(plant, [])


@router.get("/plants/{plant_id}", response_model=PlantDetail)
def get_plant_detail(
    plant_id: int,
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    plant = get_plant(db, farmer.id, plant_id)
    if not plant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plant not found")
    observations = list_observations(db, plant_id)
    insights = PlantInsights(**build_plant_insights(plant, observations))
    return PlantDetail(
        id=plant.id,
        crop=plant.crop,
        name=plant.name,
        planted_on=plant.planted_on,
        listing_id=plant.listing_id,
        created_at=plant.created_at,
        updated_at=plant.updated_at,
        observations=[_observation_out(o) for o in observations],
        insights=insights,
    )


@router.post("/plants/{plant_id}/observations", response_model=PlantObservationOut, status_code=status.HTTP_201_CREATED)
async def post_observation(
    plant_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    plant = get_plant(db, farmer.id, plant_id)
    if not plant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plant not found")
    data, filename = await _read_upload(image)
    analysis = _analyze_bytes(data, filename, crop=plant.crop)
    try:
        import io

        obs = append_observation(
            db,
            farmer_id=farmer.id,
            plant_id=plant_id,
            photo_file=io.BytesIO(data),
            filename=filename,
            analysis=analysis,
            source="tracking",
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plant not found") from exc
    return _observation_out(obs)


@router.get("/plants/{plant_id}/observations/{observation_id}/photo")
def get_observation_photo(
    plant_id: int,
    observation_id: int,
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    plant = get_plant(db, farmer.id, plant_id)
    if not plant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="plant not found")
    obs = db.get(PlantObservation, observation_id)
    if not obs or obs.plant_id != plant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="observation not found")
    try:
        path = resolve_photo_path(obs.photo_path)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found") from exc
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="photo not found")
    return FileResponse(path)


@router.post("/listings/{listing_id}/import-plant", response_model=PlantSummary, status_code=status.HTTP_201_CREATED)
def post_import_plant(
    listing_id: int,
    db: Session = Depends(get_db),
    farmer: User = Depends(_farmer_active),
):
    try:
        plant = import_plant_from_listing(db, farmer.id, listing_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="listing not found") from exc
    except ValueError as exc:
        msg = str(exc)
        if "already linked" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from exc
    return _plant_summary(plant, list_observations(db, plant.id))
