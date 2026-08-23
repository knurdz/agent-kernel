"""Unit tests for the Open-Meteo integration in tools/weather_tool.py (Increment 11.1).

Fixture-based: the shared conftest stubs `_http_get` with canned payloads,
so these tests are deterministic and network-free. The one live check is
marked `slow`. Error-reason parsing of the real transport is exercised
directly against `httpx.Response` objects (no sockets).
"""

import httpx
import pytest

import tools.weather_tool as wt
from tests.conftest import GEOCODE_FIXTURES, canned_open_meteo, forecast_payload


class CallRecorder:
    """Stub seam that records every request and can be pointed at failures."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url: str, params: dict) -> dict:
        self.calls.append((url, params))
        return canned_open_meteo(url, params)


def _expected_day(index: int, shift: float) -> dict:
    template = forecast_payload(7.0)["daily"]
    return {
        "date": template["time"][index],
        "temp_min_c": round(template["temperature_2m_min"][index] + shift, 1),
        "temp_max_c": round(template["temperature_2m_max"][index] + shift, 1),
        "rain_probability": round(template["precipitation_probability_max"][index] / 100.0, 2),
        "rain_mm": round(template["precipitation_sum"][index], 1),
        "wind_kmh": round(template["wind_speed_10m_max"][index], 1),
        "et0_mm": round(template["et0_fao_evapotranspiration"][index], 1),
    }


# ---------------------------------------------------------------------------
# Request construction
# ---------------------------------------------------------------------------


def test_geocode_uses_best_match_request_params():
    recorder = CallRecorder()
    wt._http_get = recorder

    wt._geocode("kandy")

    url, params = recorder.calls[0]
    assert url == wt.GEOCODING_URL
    assert params == {"name": "kandy", "count": 1, "language": "en"}


def test_forecast_request_carries_location_timezone_and_clamped_days():
    recorder = CallRecorder()
    wt._http_get = recorder

    wt._fetch_forecast("kandy", days=3)

    _, params = recorder.calls[-1]
    assert params["latitude"] == pytest.approx(GEOCODE_FIXTURES["kandy"]["latitude"])
    assert params["longitude"] == pytest.approx(GEOCODE_FIXTURES["kandy"]["longitude"])
    assert params["timezone"] == "Asia/Colombo"
    assert params["forecast_days"] == 3
    for variable in wt.DAILY_VARIABLES:
        assert variable in params["daily"].split(",")


def test_forecast_days_clamped_to_open_meteo_maximum():
    params = wt._forecast_params(6.58, 79.96, "Asia/Colombo", days=99)
    assert params["forecast_days"] == wt.FORECAST_DAYS_MAX
    assert wt._forecast_params(6.58, 79.96, "Asia/Colombo", days=0)["forecast_days"] == 1


# ---------------------------------------------------------------------------
# Response mapping
# ---------------------------------------------------------------------------


def test_parallel_arrays_map_onto_contract_day_dicts():
    result = wt.get_forecast("Kandy", days=3)

    assert result["reliable"] is True
    kandy_shift = round(GEOCODE_FIXTURES["kandy"]["latitude"] - 7.0, 1)
    assert result["days"] == [_expected_day(i, kandy_shift) for i in range(3)]
    first = result["days"][0]
    assert 0.0 <= first["rain_probability"] <= 1.0
    assert first["temp_min_c"] < first["temp_max_c"]


def test_geocode_empty_results_fails_fast_without_retries():
    recorder = CallRecorder()

    def no_such_place(url, params):
        recorder.calls.append((url, params))
        if "geocoding-api" in url:
            return {}
        return canned_open_meteo(url, params)

    wt._http_get = no_such_place

    result = wt.get_forecast("nowhereville")

    # One geocoding attempt only — a deterministic miss must not burn retries.
    assert len(recorder.calls) == 1
    assert result["reliable"] is False
    assert result["days"] == []
    assert "nowhereville" in result["message"]
    assert "find" in result["message"].lower()
    assert "LocationNotFoundError" in result["_error"]


def test_geocode_result_is_cached_for_process_lifetime():
    recorder = CallRecorder()
    wt._http_get = recorder

    wt.get_forecast("kandy")
    wt._fresh_cache.clear()
    wt._fresh_fetched_at.clear()
    wt.get_forecast("kandy")

    geocode_calls = [call for call in recorder.calls if "geocoding-api" in call[0]]
    assert len(geocode_calls) == 1


@pytest.mark.parametrize(
    "mutate",
    [
        lambda daily: daily.pop("et0_fao_evapotranspiration"),
        lambda daily: daily.update(wind_speed_10m_max=[9.5]),  # ragged vs time[]
        lambda daily: daily["precipitation_sum"].__setitem__(0, None),  # null value
        lambda daily: daily.pop("time"),
    ],
)
def test_broken_payloads_fail_without_fabricating_data(monkeypatch, mutate):
    payload = forecast_payload(7.2906)
    mutate(payload["daily"])

    def broken_forecast(url, params):
        if url == wt.FORECAST_URL:  # exact match: the geocoding subdomain contains this string
            return payload
        return canned_open_meteo(url, params)

    wt._http_get = broken_forecast

    result = wt.get_forecast("kandy", days=3)

    assert result["reliable"] is False
    assert result["days"] == []
    assert "could not access weather data" in result["message"].lower()


# ---------------------------------------------------------------------------
# Real-transport error handling (httpx.Response objects, no sockets)
# ---------------------------------------------------------------------------


def _response(status: int, body: bytes | None = None, json_body=None) -> httpx.Response:
    kwargs = {"request": httpx.Request("GET", wt.FORECAST_URL)}
    if json_body is not None:
        return httpx.Response(status, json=json_body, **kwargs)
    if body is not None:
        return httpx.Response(status, content=body, **kwargs)
    return httpx.Response(status, **kwargs)


def test_default_http_get_parses_reason_from_error_body(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _response(400, json_body={"error": True, "reason": "Cannot initialize WeatherVariable"})

    monkeypatch.setattr(wt.httpx, "get", fake_get)

    with pytest.raises(wt.WeatherServiceError) as excinfo:
        wt._default_http_get(wt.FORECAST_URL, {})

    assert excinfo.value.reason == "Cannot initialize WeatherVariable"


def test_default_http_get_falls_back_to_status_when_body_not_json(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _response(500, body=b"<html>gateway error</html>")

    monkeypatch.setattr(wt.httpx, "get", fake_get)

    with pytest.raises(wt.WeatherServiceError) as excinfo:
        wt._default_http_get(wt.FORECAST_URL, {})

    assert excinfo.value.reason == "HTTP 500"


def test_default_http_get_returns_parsed_json_on_success(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        return _response(200, json_body={"daily": {"ok": True}})

    monkeypatch.setattr(wt.httpx, "get", fake_get)

    assert wt._default_http_get(wt.FORECAST_URL, {}) == {"daily": {"ok": True}}


def test_service_error_takes_the_retry_then_limitation_path(monkeypatch):
    attempts = []

    def service_down(url, params):
        attempts.append(url)
        raise wt.WeatherServiceError("Cannot initialize WeatherVariable")

    wt._http_get = service_down
    monkeypatch.setattr(wt, "_sleep", lambda seconds: None)

    result = wt.get_forecast("kandy", days=3)

    assert len(attempts) == wt.RETRY_ATTEMPTS
    assert result["reliable"] is False
    assert "Cannot initialize WeatherVariable" in result["_error"]


# ---------------------------------------------------------------------------
# Short-TTL positive cache (Increment 11.1)
# ---------------------------------------------------------------------------


def test_second_call_within_ttl_is_served_cached_without_http():
    recorder = CallRecorder()
    wt._http_get = recorder

    fresh = wt.get_forecast("kandy", days=3)
    cached = wt.get_forecast("kandy", days=3)

    assert fresh["cached"] is False
    assert cached["reliable"] is True
    assert cached["cached"] is True
    assert cached["days"] == fresh["days"]
    assert cached["as_of"] == fresh["as_of"]
    assert len(recorder.calls) == 2  # geocode + forecast, once


def test_ttl_cache_disabled_by_zero_minutes(monkeypatch):
    monkeypatch.setenv("AGRIPILOT_WEATHER_CACHE_TTL_MINUTES", "0")
    recorder = CallRecorder()
    wt._http_get = recorder

    wt.get_forecast("kandy", days=3)
    second = wt.get_forecast("kandy", days=3)

    assert second["cached"] is False
    assert len(recorder.calls) == 3  # two full fetches (geocode cached after the first)


def test_ttl_cache_never_mixes_requested_day_counts():
    recorder = CallRecorder()
    wt._http_get = recorder

    three_day = wt.get_forecast("kandy", days=3)
    five_day = wt.get_forecast("kandy", days=5)

    assert five_day["cached"] is False
    assert len(five_day["days"]) == 5
    assert len(recorder.calls) == 3  # second fetch reuses the cached geocode
    # The earlier 3-day entry stays intact and independently cacheable.
    again_three = wt.get_forecast("kandy", days=3)
    assert again_three["days"] == three_day["days"]
    assert again_three["cached"] is True


# ---------------------------------------------------------------------------
# Increment 7.3 debug drift over live data
# ---------------------------------------------------------------------------


def test_conflict_debug_switch_makes_repeated_fetches_disagree(monkeypatch):
    monkeypatch.setenv("AGRIPILOT_DEBUG_WEATHER_CONFLICT", "1")
    monkeypatch.setenv("AGRIPILOT_WEATHER_CACHE_TTL_MINUTES", "0")
    wt._conflict_call_count = 0
    wt._http_get = CallRecorder()

    first = wt.get_forecast("kandy")
    second = wt.get_forecast("kandy")

    assert first["conflict"]["detected"] is False
    assert second["conflict"]["detected"] is True
    assert second["conflict"]["message"] == wt.SOURCES_DISAGREE_MESSAGE


# ---------------------------------------------------------------------------
# Live API (network + real transport)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_live_open_meteo_forecast_for_kandy(monkeypatch):
    monkeypatch.setenv("AGRIPILOT_WEATHER_CACHE_TTL_MINUTES", "0")
    monkeypatch.setattr(wt, "_http_get", wt._default_http_get)
    wt._geocode_cache.clear()

    result = wt.get_forecast("kandy", days=3)

    assert result["reliable"] is True, result.get("_error") or result.get("message")
    assert len(result["days"]) == 3
    for day in result["days"]:
        assert day["temp_min_c"] < day["temp_max_c"]
        assert 0.0 <= day["rain_probability"] <= 1.0
        assert day["rain_mm"] >= 0.0
        assert day["wind_kmh"] >= 0.0
        assert day["et0_mm"] > 0.0
