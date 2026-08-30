"""Agent tool wrapper for structured crop cultivation guides."""

from __future__ import annotations

from typing import Any, Optional

from tools.crop_guide import compute_crop_care, load_crop_guide
from tools.tool_guard import guarded


@guarded
def get_crop_guide(crop: str, planted_on: Optional[str] = None) -> dict[str, Any]:
    """Return verified cultivation, nutrient-stage, and harvest guidance for a crop.

    Use this when the farmer asks how to grow, what nutrients to apply, when to
    harvest, or how long until harvest. Numbers here match the plant tracking page.

    :param crop: Crop name (e.g. "tomato", "rice").
    :param planted_on: Optional planting date as YYYY-MM-DD for stage and countdown.
    :return: dict with "found" (bool), "guide" (crop-care fields), or "message".
    """
    guide = load_crop_guide(crop)
    if not guide:
        return {
            "found": False,
            "guide": None,
            "message": f"I do not have a verified growing guide for {crop.strip().lower()}.",
        }

    planted_date = None
    if planted_on:
        from datetime import date

        try:
            planted_date = date.fromisoformat(planted_on.strip())
        except ValueError:
            return {
                "found": False,
                "guide": None,
                "message": "planted_on must be YYYY-MM-DD when provided.",
            }

    care = compute_crop_care(crop, planted_on=planted_date)
    return {"found": True, "guide": care, "message": None}
