"""Shared fixtures: run the whole fast suite fully offline.

Every test gets the Open-Meteo HTTP seam (`tools.weather_tool._http_get`)
stubbed with canned API payloads, mirroring the documented response shape
in `plan/Open-Meteo.md`. Forecast values shift slightly with the geocoded
latitude so different locations yield different data. Tests that need the
real transport (the marked-slow live test) re-stub the seam explicitly,
and per-test overrides simply re-set `_http_get`.

The fixture also resets every weather cache before each test so results
never leak between tests via the module-level dicts.
"""

import json

import pytest

import tools.weather_tool as wt

GEOCODE_FIXTURES = {
    "kandy": {
        "id": 1239662,
        "name": "Kandy",
        "latitude": 7.2906,
        "longitude": 80.6337,
        "country": "Sri Lanka",
        "timezone": "Asia/Colombo",
        "admin1": "Central Province",
    },
    "galle": {
        "id": 1245790,
        "name": "Galle",
        "latitude": 6.0535,
        "longitude": 80.2210,
        "country": "Sri Lanka",
        "timezone": "Asia/Colombo",
        "admin1": "Southern Province",
    },
}

# Seven daily entries so day-count requests up to 7 resolve offline.
_FORECAST_TEMPLATE = {
    "latitude": 7.29,
    "longitude": 80.63,
    "timezone": "Asia/Colombo",
    "daily_units": {"time": "iso8601", "temperature_2m_max": "\u00b0C", "precipitation_sum": "mm"},
    "daily": {
        "time": ["2026-08-23", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-29"],
        "temperature_2m_max": [31.2, 30.8, 31.5, 30.9, 32.0, 31.1, 30.5],
        "temperature_2m_min": [24.1, 23.9, 24.3, 23.8, 24.6, 24.0, 23.7],
        "precipitation_sum": [0.0, 4.2, 12.5, 1.1, 0.0, 8.4, 2.3],
        "precipitation_probability_max": [10, 55, 80, 20, 5, 65, 35],
        "et0_fao_evapotranspiration": [4.1, 3.8, 3.2, 4.0, 4.2, 3.6, 3.9],
        "wind_speed_10m_max": [14.2, 18.7, 22.1, 11.8, 9.5, 16.3, 13.0],
    },
}

_FORECAST_TEMPLATE_JSON = json.dumps(_FORECAST_TEMPLATE)


def forecast_payload(latitude: float) -> dict:
    """Fresh copy of the canned forecast, shifted by geocoded latitude."""
    payload = json.loads(_FORECAST_TEMPLATE_JSON)
    shift = round(latitude - 7.0, 1)
    for variable in ("temperature_2m_max", "temperature_2m_min"):
        payload["daily"][variable] = [round(value + shift, 1) for value in payload["daily"][variable]]
    return payload


def canned_open_meteo(url: str, params: dict) -> dict:
    """Stand-in for the real transport: dispatch on endpoint subdomain."""
    if "geocoding-api.open-meteo.com" in url:
        place = str(params.get("name", "")).strip().lower()
        match = GEOCODE_FIXTURES.get(place)
        return {"results": [dict(match)]} if match else {}
    return forecast_payload(float(params["latitude"]))


@pytest.fixture(autouse=True)
def offline_open_meteo(monkeypatch):
    """Stub the HTTP seam and start every test with cold weather caches."""
    wt._geocode_cache.clear()
    wt._fresh_cache.clear()
    wt._fresh_fetched_at.clear()
    wt._cache.clear()
    monkeypatch.setattr(wt, "_http_get", canned_open_meteo)
