"""Tests for crop guides and enriched plant insights."""

from datetime import date

import pytest

from tools.crop_guide import compute_crop_care, load_crop_guide


def test_load_tomato_guide():
    guide = load_crop_guide("tomato")
    assert guide is not None
    assert guide["crop"] == "tomato"
    assert guide["days_to_harvest"]["min"] == 70


def test_unknown_crop_returns_none():
    assert load_crop_guide("durian") is None


def test_compute_crop_care_with_planted_on():
    care = compute_crop_care("tomato", planted_on=date(2026, 6, 1), reference_date=date(2026, 7, 1))
    assert care is not None
    assert care["days_since_planted"] == 30
    assert care["current_stage"]["name"] == "Vegetative"
    assert care["growth_progress"] is not None
    assert care["needs_planted_date"] is False


def test_compute_crop_care_without_planted_on():
    care = compute_crop_care("tomato")
    assert care is not None
    assert care["needs_planted_date"] is True
    assert care["current_stage"] is None
