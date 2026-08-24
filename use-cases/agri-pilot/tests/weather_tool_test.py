"""Unit tests for tools/weather_tool.py.

Since the fetch core calls the live Open-Meteo API; the
shared conftest stubs its HTTP seam with canned payloads so these tests
stay deterministic and network-free. Failure paths are exercised by
monkeypatching the `_fetch_forecast` seam.
"""

import pytest

import tools.weather_tool as wt
from tools.weather_tool import assess_irrigation_need, assess_spray_conditions, get_forecast

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


def test_repeated_calls_identical_for_same_location():
    first = get_forecast("kandy", days=2)
    second = get_forecast("Kandy", days=2)
    assert first["days"] == second["days"]
    assert second["cached"] is True  # short-TTL cache serves the repeat


def test_different_locations_give_different_data():
    a = get_forecast("kandy", days=1)["days"][0]
    b = get_forecast("galle", days=1)["days"][0]
    assert a != b


def test_day_count_respected():
    assert len(get_forecast("kandy", days=5)["days"]) == 5


# ---------------------------------------------------------------------------
# Deterministic spray-timing verdicts
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


# ---------------------------------------------------------------------------
# Failure handling: retry, cache fallback, honest limitation
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
    assert "could not access weather data" in result["message"]


def test_spray_verdict_cannot_determine_when_forecast_unavailable(monkeypatch):
    def boom(location, days):
        raise ConnectionError("api down")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: None)

    result = assess_spray_conditions("offline-village", days_ahead=1)
    assert result["verdict"] == "cannot determine"
    assert "could not access weather data" in result["reason"]


# ---------------------------------------------------------------------------
# Deterministic irrigation decision logic
#
# Water balance (et0_mm - rain_mm) decides SKIP vs deficit; probability
# only hedges an existing deficit into MONITOR at RAIN_CONFIDENCE_
# THRESHOLD; heavy rain overrides everything.
# ---------------------------------------------------------------------------


def test_irrigation_skip_when_rain_covers_water_loss(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_mm=5.0, et0_mm=4.0))
    result = assess_irrigation_need("kandy")
    assert result["verdict"] == "SKIP"
    assert result["water_deficit_mm"] == -1.0
    assert "no irrigation needed" in result["reasoning"]
    assert result["conditions"]["date"]


def test_irrigate_when_deficit_and_low_rain_chance(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_probability=0.1, rain_mm=0.0, et0_mm=4.0))
    result = assess_irrigation_need("kandy")
    assert result["verdict"] == "IRRIGATE"
    assert result["water_deficit_mm"] == 4.0
    assert "irrigate roughly 4.0 mm" in result["reasoning"]


def test_monitor_at_exact_confidence_threshold(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_probability=wt.RAIN_CONFIDENCE_THRESHOLD, rain_mm=1.0, et0_mm=4.0))
    result = assess_irrigation_need("kandy")
    assert result["verdict"] == "MONITOR"
    assert result["water_deficit_mm"] == 3.0
    assert "check again" in result["reasoning"]


def test_irrigate_just_below_confidence_threshold(monkeypatch):
    _stub_forecast(monkeypatch, _day(rain_probability=wt.RAIN_CONFIDENCE_THRESHOLD - 0.01, rain_mm=1.0, et0_mm=4.0))
    assert assess_irrigation_need("kandy")["verdict"] == "IRRIGATE"


def test_heavy_rain_overrides_balance_math(monkeypatch):
    # Deficit says IRRIGATE, but 25 mm rain means never add water.
    _stub_forecast(monkeypatch, _day(rain_probability=0.1, rain_mm=25.0, et0_mm=6.0))
    result = assess_irrigation_need("kandy")
    assert result["verdict"] == "HEAVY_RAIN"
    assert "do not add irrigation" in result["reasoning"]


def test_irrigation_cannot_determine_without_forecast(monkeypatch):
    def boom(location, days):
        raise ConnectionError("api down")

    monkeypatch.setattr(wt, "_fetch_forecast", boom)
    monkeypatch.setattr(wt, "_sleep", lambda s: None)

    result = assess_irrigation_need("offline-village")
    assert result["verdict"] == "CANNOT DETERMINE"
    assert "could not access weather data" in result["reason"]


def test_range_query_reports_summary_and_per_day(monkeypatch):
    week = [
        _day(date="2026-08-23", rain_probability=0.1, rain_mm=0.0, et0_mm=4.0),  # IRRIGATE (+4)
        _day(date="2026-08-24", rain_probability=0.1, rain_mm=6.0, et0_mm=4.0),  # SKIP (-2)
        _day(date="2026-08-25", rain_probability=0.9, rain_mm=1.0, et0_mm=4.0),  # MONITOR (+3)
    ]
    monkeypatch.setattr(wt, "_fetch_forecast", lambda location, count: {"days": week})

    result = assess_irrigation_need("kandy", num_days=3)

    assert set(result) >= {"range_summary", "per_day"}
    summary = result["range_summary"]
    assert summary["verdict"] == "IRRIGATE"
    assert summary["cumulative_deficit_mm"] == 5.0
    assert summary["excluded_days"] == []
    assert [day["verdict"] for day in result["per_day"]] == ["IRRIGATE", "SKIP", "MONITOR"]
    assert [day["date"] for day in result["per_day"]] == [d["date"] for d in week]
    assert all(set(day) == {"date", "verdict", "water_deficit_mm"} for day in result["per_day"])
    assert "5.0 mm" in summary["reasoning"]


def test_range_summary_skips_when_cumulative_balance_nonpositive(monkeypatch):
    week = [
        _day(date="2026-08-23", rain_probability=0.1, rain_mm=0.0, et0_mm=4.0),  # IRRIGATE (+4)
        _day(date="2026-08-24", rain_probability=0.1, rain_mm=8.0, et0_mm=4.0),  # SKIP (-4)
        _day(date="2026-08-25", rain_probability=0.1, rain_mm=5.0, et0_mm=4.0),  # SKIP (-1)
    ]
    monkeypatch.setattr(wt, "_fetch_forecast", lambda location, count: {"days": week})

    result = assess_irrigation_need("kandy", num_days=3)

    assert result["range_summary"]["cumulative_deficit_mm"] == -1.0
    assert result["range_summary"]["verdict"] == "SKIP"


def test_range_summary_warns_on_heavy_rain_day(monkeypatch):
    week = [
        _day(date="2026-08-23", rain_probability=0.1, rain_mm=0.0, et0_mm=12.0),  # IRRIGATE (+12)
        _day(date="2026-08-24", rain_probability=0.95, rain_mm=25.0, et0_mm=4.0),  # HEAVY_RAIN (-21)
        _day(date="2026-08-25", rain_probability=0.1, rain_mm=0.0, et0_mm=12.0),  # IRRIGATE (+12)
    ]
    monkeypatch.setattr(wt, "_fetch_forecast", lambda location, count: {"days": week})

    result = assess_irrigation_need("kandy", num_days=3)

    # Balance math still says IRRIGATE overall, but the heavy-rain day
    # must be called out so the farmer never waters on top of it.
    assert result["range_summary"]["cumulative_deficit_mm"] == 3.0
    assert result["range_summary"]["verdict"] == "IRRIGATE"
    assert "heavy rain" in result["range_summary"]["reasoning"].lower()
    assert "do not add" in result["range_summary"]["reasoning"]
    heavy_entry = next(day for day in result["per_day"] if day["verdict"] == "HEAVY_RAIN")
    assert "do not add irrigation" in heavy_entry["warning"]


def test_single_day_beyond_horizon_cannot_determine():
    result = assess_irrigation_need("kandy", days_ahead=wt.FORECAST_DAYS_MAX)
    assert result["verdict"] == "CANNOT DETERMINE"
    assert str(wt.FORECAST_DAYS_MAX) in result["reason"]


def test_range_crossing_horizon_is_truncated_with_note(monkeypatch):
    fetched = []

    def record(location, days):
        fetched.append(days)
        return {"days": [_day(date=f"2026-09-{10 + i:02d}") for i in range(days)]}

    monkeypatch.setattr(wt, "_fetch_forecast", record)

    result = assess_irrigation_need("kandy", days_ahead=14, num_days=7)

    assert fetched == [wt.FORECAST_DAYS_MAX]
    assert len(result["per_day"]) == wt.FORECAST_DAYS_MAX - 14
    assert "note" in result
    assert "not assessed" in result["note"]


def test_num_days_clamped_to_range_maximum(monkeypatch):
    fetched = []
    week = [_day(date=f"2026-08-{23 + i}") for i in range(10)]

    def record(location, days):
        fetched.append(days)
        return {"days": week}

    monkeypatch.setattr(wt, "_fetch_forecast", record)

    result = assess_irrigation_need("kandy", num_days=30)

    assert fetched == [wt.IRRIGATION_RANGE_DAYS_MAX]
    assert len(result["per_day"]) == wt.IRRIGATION_RANGE_DAYS_MAX


def test_mapper_rejects_implausible_et0_as_data_anomaly():
    payload = {
        "daily": {
            "time": ["2026-08-23", "2026-08-24"],
            "temperature_2m_max": [30.0, 31.0],
            "temperature_2m_min": [20.0, 21.0],
            "precipitation_sum": [0.0, 1.0],
            "precipitation_probability_max": [10, 20],
            # Second day's zero ET0 is physically implausible.
            "et0_fao_evapotranspiration": [4.0, 0.0],
            "wind_speed_10m_max": [10.0, 11.0],
        }
    }

    with pytest.raises(ValueError, match="implausible"):
        wt._map_daily_response(payload, days=2)
