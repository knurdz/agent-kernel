"""Unit tests for tools/market_tool.py (Increments 6.1, 6.3).

The mock is deterministic (sha256-seeded per crop+market), so no fixtures
or network are needed. Staleness (Increment 6.3) is exercised by
monkeypatching the `_fetch_prices` seam to return an `as_of` of our
choosing — the same injection pattern as weather_tool's `_fetch_forecast`.
"""

from datetime import datetime, timedelta

import pytest

import tools.market_tool as mt
from tools.market_tool import STALE_AFTER_HOURS, get_price

REQUIRED_OPTION_FIELDS = {"market", "price_per_kg"}


def _as_of(hours_ago: float) -> str:
    return (datetime.now() - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def _stub_fetch(monkeypatch, hours_ago: float = 0.0):
    def fake(crop_key, location_key):
        fetched = mt._mock_prices(crop_key, location_key)
        fetched["as_of"] = _as_of(hours_ago)
        return fetched

    monkeypatch.setattr(mt, "_fetch_prices", fake)


# ---------------------------------------------------------------------------
# Increment 6.1 — documented envelope schema
# ---------------------------------------------------------------------------


def test_return_shape_matches_documented_schema():
    result = get_price("Tomato", "Kandy")

    assert set(result) >= {
        "reliable",
        "crop",
        "location",
        "as_of",
        "data_freshness",
        "options",
        "message",
    }
    assert result["reliable"] is True
    assert result["message"] is None
    assert result["crop"] == "tomato"  # normalized to lowercase
    assert result["location"] == "kandy"
    assert result["data_freshness"] == "current"
    assert len(result["options"]) == len(mt._MOCK_MARKETS)
    for option in result["options"]:
        assert REQUIRED_OPTION_FIELDS <= set(option)
        assert option["price_per_kg"] > 0.0


def test_no_revenue_field_when_quantity_not_given():
    for option in get_price("tomato", "kandy")["options"]:
        assert "estimated_revenue" not in option


def test_deterministic_for_same_crop_across_calls_and_processes():
    first = get_price("tomato", "kandy")
    second = get_price("TOMATO", "Galle")
    assert first["options"] == second["options"]

    # sha256 seeding must not depend on process-level salted hash(): a
    # fresh interpreter yields identical values.
    import subprocess
    import sys

    code = "from tools.market_tool import get_price;" "print(get_price('tomato', 'kandy')['options'])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert str(first["options"]) in out.stdout


def test_different_crops_give_different_data():
    tomato = get_price("tomato", "kandy")["options"]
    onion = get_price("onion", "kandy")["options"]
    assert tomato != onion


# ---------------------------------------------------------------------------
# Increment 6.1 — revenue formula: round(price_per_kg * quantity_kg, 2)
# ---------------------------------------------------------------------------


def test_estimated_revenue_follows_stated_formula():
    result = get_price("tomato", "kandy", quantity_kg=500)

    for option in result["options"]:
        assert option["estimated_revenue"] == round(option["price_per_kg"] * 500, 2)


def test_fractional_quantity_rounds_to_two_decimals():
    result = get_price("onion", "kandy", quantity_kg=12.345)
    for option in result["options"]:
        assert option["estimated_revenue"] == round(option["price_per_kg"] * 12.345, 2)


@pytest.mark.parametrize("bad", [0, -5, "many", True])
def test_invalid_quantity_raises_value_error(bad):
    with pytest.raises(ValueError):
        get_price("tomato", "kandy", quantity_kg=bad)


# ---------------------------------------------------------------------------
# Increment 6.1 — no-data paths: never fabricate prices
# ---------------------------------------------------------------------------


def test_unknown_crop_returns_limitation_without_options():
    result = get_price("dragonfruit", "kandy")

    assert result["reliable"] is False
    assert result["options"] == []
    assert result["as_of"] is None
    assert result["data_freshness"] is None
    assert "dragonfruit" in result["message"]
    assert "don't have" in result["message"].lower()


def test_blank_crop_asks_for_crop():
    result = get_price("   ", "kandy")
    assert result["reliable"] is False
    assert result["options"] == []
    assert "crop" in result["message"].lower()


def test_plural_crop_phrasing_matches_catalog():
    result = get_price("tomatoes", "kandy")
    assert result["reliable"] is True
    assert result["crop"] == "tomato"
    assert len(result["options"]) >= 1


def test_unknown_stays_unknown_despite_plural_rule():
    assert get_price("potatoesq", "kandy")["reliable"] is False


def test_blank_location_asks_for_location():
    result = get_price("tomato")
    assert result["reliable"] is False
    assert result["options"] == []
    assert "location" in result["message"].lower()


# ---------------------------------------------------------------------------
# Increment 6.3 — staleness handling via the _fetch_prices seam
# ---------------------------------------------------------------------------


def test_recent_data_is_current(monkeypatch):
    _stub_fetch(monkeypatch, hours_ago=1.0)
    assert get_price("tomato", "kandy")["data_freshness"] == "current"


def test_data_older_than_threshold_is_stale(monkeypatch):
    _stub_fetch(monkeypatch, hours_ago=STALE_AFTER_HOURS + 1.0)
    result = get_price("tomato", "kandy")
    assert result["data_freshness"] == "stale"


def test_boundary_exactly_at_threshold_is_current(monkeypatch):
    # Freeze the clock so the exact boundary is deterministic: stale iff
    # age is strictly greater than STALE_AFTER_HOURS.
    fixed_now = datetime(2026, 8, 22, 12, 0, 0)
    monkeypatch.setattr(mt, "_now", lambda: fixed_now)

    def fake(crop_key, location_key):
        fetched = mt._mock_prices(crop_key, location_key)
        fetched["as_of"] = (fixed_now - timedelta(hours=STALE_AFTER_HOURS)).isoformat(timespec="seconds")
        return fetched

    monkeypatch.setattr(mt, "_fetch_prices", fake)
    assert get_price("tomato", "kandy")["data_freshness"] == "current"


def test_boundary_one_second_past_threshold_is_stale(monkeypatch):
    fixed_now = datetime(2026, 8, 22, 12, 0, 0)
    monkeypatch.setattr(mt, "_now", lambda: fixed_now)

    def fake(crop_key, location_key):
        fetched = mt._mock_prices(crop_key, location_key)
        fetched["as_of"] = (fixed_now - timedelta(hours=STALE_AFTER_HOURS, seconds=1)).isoformat(timespec="seconds")
        return fetched

    monkeypatch.setattr(mt, "_fetch_prices", fake)
    assert get_price("tomato", "kandy")["data_freshness"] == "stale"
