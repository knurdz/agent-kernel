"""Unit tests for tools/weather_tool.py (Increment 5.1).

The mock is deterministic (sha256-seeded per location), so no fixtures or
network are needed. Failure paths (Increment 5.4) are exercised by
monkeypatching the `_fetch_forecast` seam.
"""

import pytest

import tools.weather_tool as wt
from tools.weather_tool import assess_spray_conditions, get_forecast

REQUIRED_DAY_FIELDS = {
    "date",
    "temp_min_c",
    "temp_max_c",
    "rain_probability",
    "rain_mm",
    "wind_kmh",
    "et0_mm",
}


def test_return_shape_matches_documented_schema():
    result = get_forecast("Kandy", days=3)

    assert set(result) >= {"reliable", "location", "cached", "days", "message"}
    assert result["reliable"] is True
    assert result["cached"] is False
    assert result["message"] is None
    # location normalized to lowercase
    assert result["location"] == "kandy"
    assert len(result["days"]) == 3
    for day in result["days"]:
        assert REQUIRED_DAY_FIELDS <= set(day)
        assert 0.0 <= day["rain_probability"] <= 1.0
        assert day["temp_min_c"] < day["temp_max_c"]
        assert day["rain_mm"] >= 0.0
        assert day["et0_mm"] > 0.0


def test_deterministic_for_same_location_across_calls_and_processes():
    first = get_forecast("kandy", days=2)
    second = get_forecast("Kandy", days=2)
    assert first["days"] == second["days"]

    one = get_forecast("kandy", days=1)["days"][0]

    # sha256 seeding must not depend on process-level salted hash(): a
    # fresh interpreter yields identical values.
    import subprocess
    import sys

    code = "from tools.weather_tool import get_forecast;" "print(get_forecast('kandy', days=1)['days'][0])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert str(one) in out.stdout


def test_different_locations_give_different_data():
    a = get_forecast("kandy", days=1)["days"][0]
    b = get_forecast("galle", days=1)["days"][0]
    assert a != b


def test_day_count_respected():
    assert len(get_forecast("kandy", days=5)["days"]) == 5


# ---------------------------------------------------------------------------
# Increment 5.3 — deterministic spray-timing verdicts
# ---------------------------------------------------------------------------


def _day(**overrides):
    day = {
        "date": "2026-08-23",
        "temp_min_c": 20.0,
        "temp_max_c": 30.0,
        "rain_probability": 0.1,
        "rain_mm": 0.0,
        "wind_kmh": 5.0,
        "et0_mm": 4.0,
    }
    day.update(overrides)
    return day


def _stub_forecast(monkeypatch, day):
    monkeypatch.setattr(wt, "_fetch_forecast", lambda location, days: {"days": [day] * days})


def test_spray_suitable_when_dry_and_calm(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_probability=0.1, rain_mm=0.0, wind_kmh=5.0))
    result = assess_spray_conditions("kandy", days_ahead=1)
    assert result["verdict"] == "suitable"
    assert result["conditions"] is not None
    assert "wind" in result["reason"].lower()


def test_spray_not_suitable_when_rain_likely(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_probability=0.8, rain_mm=12.0))
    result = assess_spray_conditions("kandy")
    assert result["verdict"] == "not suitable"
    assert "wash" in result["reason"].lower()


def test_spray_not_suitable_when_windy(monkeypatch):
    _stub_forecast(monkeypatch, _day(wind_kmh=22.0))
    result = assess_spray_conditions("kandy")
    assert result["verdict"] == "not suitable"
    assert "drift" in result["reason"].lower()


@pytest.fixture(autouse=True)
def _clear_cache():
    wt._cache.clear()
    yield
    wt._cache.clear()


# ---------------------------------------------------------------------------
# Increment 5.4 — failure handling: retry, cache fallback, honest limitation
# ---------------------------------------------------------------------------


def test_retries_with_backoff_before_giving_up(monkeypatch):
    calls, sleeps = [], []

    def boom(location, days):
        calls.append((location, days))
        raise ConnectionError("api down")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: sleeps.append(s))

    result = get_forecast("kandy")

    assert len(calls) == wt.RETRY_ATTEMPTS
    assert sleeps == [0.5 * (i + 1) for i in range(wt.RETRY_ATTEMPTS - 1)]
    assert result["reliable"] is False


def test_cached_fallback_after_failure_is_marked_cached(monkeypatch):
    good = get_forecast("kandy")
    assert good["cached"] is False

    def boom(location, days):
        raise TimeoutError("timeout")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: None)

    fallback = get_forecast("kandy")

    assert fallback["reliable"] is True
    assert fallback["cached"] is True
    assert fallback["days"] == good["days"]
    # as_of still records when the data was originally fetched.
    assert fallback["as_of"] == good["as_of"]


def test_no_cache_states_limitation_instead_of_guessing(monkeypatch):
    def boom(location, days):
        raise ConnectionError("api down")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: None)

    result = get_forecast("never-fetched-town")

    assert result["reliable"] is False
    assert result["days"] == []
    assert "cannot" in result["message"].lower() or "try again" in result["message"].lower()
    assert "reliable weather forecast" in result["message"]


def test_spray_verdict_cannot_determine_when_forecast_unavailable(monkeypatch):
    def boom(location, days):
        raise ConnectionError("api down")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: None)

    result = assess_spray_conditions("offline-village", days_ahead=1)
    assert result["verdict"] == "cannot determine"
    assert "forecast" in result["reason"].lower()
