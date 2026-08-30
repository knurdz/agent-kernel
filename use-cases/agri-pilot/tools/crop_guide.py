"""Structured crop cultivation guides for tracking insights and agent tools."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Optional

GUIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "crop_guides"


def _normalize_crop(crop: str) -> str:
    return crop.strip().lower()


def list_supported_crops() -> list[str]:
    if not GUIDES_DIR.is_dir():
        return []
    return sorted(p.stem for p in GUIDES_DIR.glob("*.json"))


def load_crop_guide(crop: str) -> Optional[dict[str, Any]]:
    """Load a crop guide JSON by crop name, or None if unsupported."""
    path = GUIDES_DIR / f"{_normalize_crop(crop)}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _stage_for_day(guide: dict[str, Any], day: int) -> Optional[dict[str, Any]]:
    for stage in guide.get("stages") or []:
        start = int(stage.get("day_start", 0))
        end = int(stage.get("day_end", start))
        if start <= day <= end:
            return stage
    stages = guide.get("stages") or []
    if stages and day > int(stages[-1].get("day_end", 0)):
        return stages[-1]
    return stages[0] if stages else None


def compute_crop_care(
    crop: str,
    *,
    planted_on: Optional[date] = None,
    reference_date: Optional[date] = None,
) -> Optional[dict[str, Any]]:
    """Derive tracking-friendly crop-care fields from a guide."""
    guide = load_crop_guide(crop)
    if not guide:
        return None

    ref = reference_date or date.today()
    days_min = int((guide.get("days_to_harvest") or {}).get("min", 0))
    days_max = int((guide.get("days_to_harvest") or {}).get("max", days_min))

    days_since_planted: Optional[int] = None
    harvest_window_start: Optional[str] = None
    harvest_window_end: Optional[str] = None
    days_to_harvest_min: Optional[int] = None
    days_to_harvest_max: Optional[int] = None
    growth_progress: Optional[float] = None
    current_stage: Optional[dict[str, Any]] = None

    if planted_on is not None:
        days_since_planted = max(0, (ref - planted_on).days)
        harvest_start = planted_on.toordinal() + days_min
        harvest_end = planted_on.toordinal() + days_max
        harvest_window_start = date.fromordinal(harvest_start).isoformat()
        harvest_window_end = date.fromordinal(harvest_end).isoformat()
        days_to_harvest_min = max(0, days_min - days_since_planted)
        days_to_harvest_max = max(0, days_max - days_since_planted)
        if days_max > 0:
            growth_progress = round(min(1.0, days_since_planted / days_max), 3)
        stage = _stage_for_day(guide, days_since_planted)
        if stage:
            current_stage = {
                "id": stage.get("id"),
                "name": stage.get("name"),
                "watering": stage.get("watering"),
                "nutrients": stage.get("nutrients"),
            }

    return {
        "crop": guide.get("crop", _normalize_crop(crop)),
        "source": guide.get("source"),
        "days_to_harvest_min": days_min,
        "days_to_harvest_max": days_max,
        "spacing": guide.get("spacing"),
        "how_to_grow": guide.get("how_to_grow"),
        "harvest_signs": guide.get("harvest_signs"),
        "days_since_planted": days_since_planted,
        "harvest_window_start": harvest_window_start,
        "harvest_window_end": harvest_window_end,
        "days_to_harvest_min_remaining": days_to_harvest_min,
        "days_to_harvest_max_remaining": days_to_harvest_max,
        "growth_progress": growth_progress,
        "current_stage": current_stage,
        "needs_planted_date": planted_on is None,
    }


def guide_to_chroma_records(guide: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand one guide into cultivation / nutrients / harvest Chroma documents."""
    crop = guide.get("crop", "")
    source = guide.get("source", "")
    records: list[dict[str, Any]] = []

    cultivation_body = "\n".join(
        part
        for part in [
            f"# Growing {crop.title()}",
            guide.get("how_to_grow", ""),
            f"Spacing: {guide.get('spacing', '')}" if guide.get("spacing") else "",
            f"Typical days to harvest: {guide.get('days_to_harvest', {}).get('min', '?')}"
            f"–{guide.get('days_to_harvest', {}).get('max', '?')} from transplant or establishment.",
        ]
        if part
    )
    records.append(
        {
            "text": cultivation_body.strip(),
            "metadata": {"crop": crop, "topic": "cultivation", "source": source},
        }
    )

    nutrient_lines = []
    for stage in guide.get("stages") or []:
        nutrient_lines.append(
            f"## {stage.get('name')} (days {stage.get('day_start')}–{stage.get('day_end')})\n"
            f"Watering: {stage.get('watering', '')}\n"
            f"Nutrients: {stage.get('nutrients', '')}"
        )
    records.append(
        {
            "text": f"# Nutrients and watering for {crop.title()}\n\n" + "\n\n".join(nutrient_lines),
            "metadata": {"crop": crop, "topic": "nutrients", "source": source},
        }
    )

    harvest_body = "\n".join(
        part
        for part in [
            f"# Harvesting {crop.title()}",
            guide.get("harvest_signs", ""),
            f"Expected harvest window: {guide.get('days_to_harvest', {}).get('min', '?')}"
            f"–{guide.get('days_to_harvest', {}).get('max', '?')} days after planting or transplant.",
        ]
        if part
    )
    records.append(
        {
            "text": harvest_body.strip(),
            "metadata": {"crop": crop, "topic": "harvest", "source": source},
        }
    )
    return records
