"""Weather tools for AgriPilot (Increments 5.1, 5.4, 11.1).

`get_forecast` is the single source of forecast data for the resource
agent. Increment 11.1 swapped the deterministic mock for the live
Open-Meteo API behind the exact same return shape, so the schema below is
a contract — do not change it casually:

    {
        "reliable": True,
        "location": "kandy",          # normalized (lowercase) location
        "cached": False,              # True when served from a cache/fallback
        "as_of": "2026-08-22T10:30:00",  # when the data was fetched
        "days": [
            {
                "date": "2026-08-22",
                "temp_min_c": 21.4,
                "temp_max_c": 30.8,
                "rain_probability": 0.65,   # 0.0-1.0
                "rain_mm": 8.2,             # expected rainfall, mm/day
                "wind_kmh": 7.5,
                "et0_mm": 3.9,              # reference evapotranspiration, mm/day
            },
            ...  # one entry per requested day, starting today
        ],
        "message": None,              # farmer-facing limitation message on failure
        "conflict": None,             # Increment 7.3: {"detected", "details", "message"}
    }

Data source: Open-Meteo (https://open-meteo.com) — free for non-commercial
use, no API key; see `plan/Open-Meteo.md`. Two calls per fresh fetch:
place name -> lat/lon via the geocoding endpoint (results cached forever —
towns don't move), then the forecast endpoint for the mapped daily
variables.

On failure the tool never invents numbers: transient HTTP/network errors
retry with backoff, then fall back to the last cached forecast for that
location (`reliable=True, cached=True`) or report `reliable=False` with a
limitation `message` (Increment 5.4). A location the geocoder does not
know fails fast with its own message instead of burning retries.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Callable, Optional

import httpx

from tools.tool_guard import guarded

FORECAST_DAYS_DEFAULT = 3
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
HTTP_TIMEOUT_SECONDS = 10.0

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Daily variables mapped into the contract below. Only what the resource
# agent reasons over — larger lists grow the payload for no benefit.
DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "et0_fao_evapotranspiration",
    "wind_speed_10m_max",
)
FORECAST_DAYS_MAX = 16  # Open-Meteo hard limit

SPRAY_MAX_RAIN_PROBABILITY = 0.3
SPRAY_MAX_RAIN_MM = 2.0
SPRAY_MAX_WIND_KMH = 15.0

# Increment 7.3: a fresh forecast "conflicts" with the previously cached
# one for the same location when any overlapping field differs by more
# than these tolerances. With live data natural drift between fetches can
# trip these; AGRIPILOT_DEBUG_WEATHER_CONFLICT=1 forces divergent readings
# deterministically so the path stays manually testable.
CONFLICT_TOLERANCES = {
    "temp_min_c": 1.0,
    "temp_max_c": 1.0,
    "rain_probability": 0.10,
    "rain_mm": 2.0,
    "wind_kmh": 3.0,
    "et0_mm": 1.0,
}

SOURCES_DISAGREE_MESSAGE = (
    "Weather sources are giving conflicting readings for your area right "
    "now, so I cannot advise reliably. Please ask again a little later."
)

NO_FORECAST_MESSAGE = (
    "I could not access weather data for your area right now, " "so I cannot advise on this. Please try again later."
)

UNRECOGNIZED_LOCATION_MESSAGE = (
    'I couldn\'t find weather information for "{location}". Please '
    "double-check the town or district name and try again."
)

CANNOT_DETERMINE_MESSAGE = "I need your location to check the weather conditions before I can " "advise on spraying."

_sleep: Callable[[float], None] = time.sleep


class LocationNotFoundError(Exception):
    """The geocoding service answered but knows no such place.

    Deterministic failure: retried attempts would return the same answer,
    so `get_forecast` reports it without burning retries/backoff.
    """


class WeatherServiceError(Exception):
    """Open-Meteo answered with an HTTP error (`error: true` body).

    Carries the API's human-readable `reason` when the error body parses;
    treated like any other transient failure by the retry logic.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _location_key(location: str) -> str:
    """Normalize a free-text location to a stable cache/geocode key."""
    return location.strip().lower()


def _cache_ttl_seconds() -> float:
    """Positive-cache window from env; <= 0 disables the short-TTL cache."""
    raw = os.environ.get("AGRIPILOT_WEATHER_CACHE_TTL_MINUTES")
    try:
        minutes = float(raw) if raw else 60.0
    except ValueError:
        minutes = 60.0
    return max(minutes, 0.0) * 60.0


# Plain module-level dicts without locking: under CPython/GIL single dict
# operations are effectively atomic and every fill here is idempotent, so
# the worst concurrent outcome is a redundant fetch or a marginally stale
# hit — never corruption or fabricated data (same characteristics as the
# long-standing `_cache`). Revisit with a threading.Lock only on evidence
# of real contention.
_geocode_cache: dict[str, tuple[float, float, Optional[str]]] = {}
_fresh_cache: dict[tuple[str, int], dict[str, Any]] = {}
_fresh_fetched_at: dict[tuple[str, int], float] = {}
_cache: dict[str, dict[str, Any]] = {}

_http_get: Callable[[str, dict[str, Any]], dict[str, Any]]


def _default_http_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """Plain GET returning parsed JSON, with Open-Meteo reasons surfaced."""
    try:
        response = httpx.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        reason: Optional[str] = None
        try:
            body = exc.response.json()
            if isinstance(body, dict):
                value = body.get("reason")
                if isinstance(value, str):
                    reason = value
        except Exception:  # noqa: BLE001 - error body may not be JSON at all
            pass
        raise WeatherServiceError(reason or f"HTTP {exc.response.status_code}") from exc
    return response.json()


_http_get = _default_http_get


def _geocode(location_key: str) -> tuple[float, float, Optional[str]]:
    """Resolve a normalized place name to (lat, lon, IANA timezone).

    Results are cached for the process lifetime — towns don't move.
    """
    cached = _geocode_cache.get(location_key)
    if cached is not None:
        return cached
    if len(location_key) < 2:  # API requires at least 2 characters
        raise LocationNotFoundError(f"location too short: {location_key!r}")
    payload = _http_get(GEOCODING_URL, {"name": location_key, "count": 1, "language": "en"})
    results = payload.get("results") or []
    if not isinstance(results, list) or not results:
        raise LocationNotFoundError(f"no geocoding match for {location_key!r}")
    first = results[0]
    resolved = (float(first["latitude"]), float(first["longitude"]), first.get("timezone"))
    _geocode_cache[location_key] = resolved
    return resolved


def _forecast_params(latitude: float, longitude: float, timezone: Optional[str], days: int) -> dict[str, Any]:
    clamped = min(max(days, 1), FORECAST_DAYS_MAX)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join(DAILY_VARIABLES),
        "forecast_days": clamped,
        # Always pin local time so daily boundaries match the farmer's
        # calendar (GMT defaults would mis-aggregate UTC+5:30 Sri Lanka).
        "timezone": timezone or "auto",
    }


def _require_number(value: Any, variable: str, iso_date: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"missing or invalid {variable} for {iso_date}: {value!r}")
    return float(value)


def _map_daily_response(payload: dict[str, Any], days: int) -> list[dict[str, Any]]:
    """Map Open-Meteo's parallel arrays onto the contract's day dicts.

    Any structural surprise (missing keys, ragged arrays, null values)
    raises, so the retry/fallback machinery treats it like any other
    failed fetch — never fabricate weather data.
    """
    daily = payload.get("daily")
    if not isinstance(daily, dict):
        raise ValueError("forecast response has no daily block")
    times = daily.get("time")
    if not isinstance(times, list) or len(times) < days:
        raise ValueError("daily.time missing or shorter than requested days")
    series: dict[str, list[Any]] = {}
    for variable in DAILY_VARIABLES:
        column = daily.get(variable)
        if not isinstance(column, list) or len(column) != len(times):
            raise ValueError(f"daily.{variable} missing or ragged against daily.time")
        series[variable] = column
    out: list[dict[str, Any]] = []
    for index in range(days):
        iso_date = str(times[index])
        out.append(
            {
                "date": iso_date,
                "temp_min_c": round(
                    _require_number(series["temperature_2m_min"][index], "temperature_2m_min", iso_date), 1
                ),
                "temp_max_c": round(
                    _require_number(series["temperature_2m_max"][index], "temperature_2m_max", iso_date), 1
                ),
                "rain_probability": round(
                    _require_number(
                        series["precipitation_probability_max"][index], "precipitation_probability_max", iso_date
                    )
                    / 100.0,
                    2,
                ),
                "rain_mm": round(_require_number(series["precipitation_sum"][index], "precipitation_sum", iso_date), 1),
                "wind_kmh": round(
                    _require_number(series["wind_speed_10m_max"][index], "wind_speed_10m_max", iso_date), 1
                ),
                "et0_mm": round(
                    _require_number(
                        series["et0_fao_evapotranspiration"][index], "et0_fao_evapotranspiration", iso_date
                    ),
                    1,
                ),
            }
        )
    return out


def _fetch_forecast(location: str, days: int) -> dict[str, list[dict[str, Any]]]:
    """Fetch core, separated from retry/cache so tests can inject failures.

    Geocodes the normalized location (cached), pulls the daily forecast
    and maps it onto the contract shape. With
    AGRIPILOT_DEBUG_WEATHER_CONFLICT=1 the mapped readings drift further
    apart on every call so repeated fetches disagree (Increment 7.3
    manual testing).
    """
    latitude, longitude, timezone = _geocode(location)
    payload = _http_get(FORECAST_URL, _forecast_params(latitude, longitude, timezone, days))
    days_mapped = _map_daily_response(payload, min(max(days, 1), FORECAST_DAYS_MAX))
    if os.environ.get("AGRIPILOT_DEBUG_WEATHER_CONFLICT") == "1":
        global _conflict_call_count
        _conflict_call_count += 1
        drift = _conflict_call_count - 1
        for day in days_mapped:
            day["temp_min_c"] = round(day["temp_min_c"] + 6.0 * drift, 1)
            day["temp_max_c"] = round(day["temp_max_c"] + 6.0 * drift, 1)
            day["rain_probability"] = round(min(1.0, day["rain_probability"] + 0.45 * drift), 2)
            day["rain_mm"] = round(day["rain_mm"] + 10.0 * drift, 1)
    return {"days": days_mapped}


_conflict_call_count = 0


@guarded
def _detect_conflicts(previous_days: list[dict[str, Any]], current_days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare overlapping forecast days and report material disagreements.

    Only fields with a tolerance in CONFLICT_TOLERANCES are compared; a
    difference beyond the tolerance counts as one conflict detail.
    """
    previous_by_date = {day.get("date"): day for day in previous_days}
    details: list[dict[str, Any]] = []
    for day in current_days:
        old_day = previous_by_date.get(day.get("date"))
        if old_day is None:
            continue
        for field_name, tolerance in CONFLICT_TOLERANCES.items():
            old_value = old_day.get(field_name)
            new_value = day.get(field_name)
            if isinstance(old_value, (int, float)) and isinstance(new_value, (int, float)):
                if abs(new_value - old_value) > tolerance:
                    details.append(
                        {
                            "date": day["date"],
                            "field": field_name,
                            "previous": old_value,
                            "current": new_value,
                        }
                    )
    return details


def get_forecast(location: str, days: int = FORECAST_DAYS_DEFAULT) -> dict[str, Any]:
    """Return a daily weather forecast for a location.

    Call this with the farmer's location before any irrigation or spray
    advice. If `reliable` is false, relay `message` to the farmer instead
    of guessing conditions. When `cached` is true the data is from an
    earlier fetch (`as_of`) — say so plainly in your reply.

    :param location: Farmer's location (e.g. a town or district name).
    :param days: Number of forecast days, starting today.
    :return: The documented forecast envelope (see module docstring).
    """
    key = _location_key(location)
    ttl_key = (key, days)

    # Short-TTL positive cache (Increment 11.1): repeated questions about
    # the same location/day-count inside the window skip the network
    # entirely and stay comfortably within Open-Meteo's free-tier limits.
    ttl_seconds = _cache_ttl_seconds()
    fetched_at = _fresh_fetched_at.get(ttl_key)
    if ttl_seconds > 0 and fetched_at is not None and (time.monotonic() - fetched_at) < ttl_seconds:
        return {**_fresh_cache[ttl_key], "cached": True}

    last_error: Optional[Exception] = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            fetched = _fetch_forecast(key, days)
            previous = _cache.get(key)
            conflicts = (
                _detect_conflicts(previous.get("days") or [], fetched["days"])
                if previous and previous.get("reliable")
                else []
            )
            result: dict[str, Any] = {
                "reliable": True,
                "location": key,
                "cached": False,
                "as_of": datetime.now().isoformat(timespec="seconds"),
                **fetched,
                "message": None,
                # Increment 7.3: never silently pick between disagreeing
                # readings — surface the conflict for the agent to relay.
                "conflict": {
                    "detected": bool(conflicts),
                    "details": conflicts,
                    "message": SOURCES_DISAGREE_MESSAGE if conflicts else None,
                },
            }
            _cache[key] = result
            _fresh_cache[ttl_key] = result
            _fresh_fetched_at[ttl_key] = time.monotonic()
            return result
        except LocationNotFoundError as exc:
            last_error = exc
            break  # deterministic miss: retries would repeat the answer
        except Exception as exc:  # noqa: BLE001 - any fetch failure triggers retry/fallback
            last_error = exc
            if attempt < RETRY_ATTEMPTS - 1:
                _sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

    if isinstance(last_error, LocationNotFoundError):
        return {
            "reliable": False,
            "location": key,
            "cached": False,
            "as_of": None,
            "days": [],
            "message": UNRECOGNIZED_LOCATION_MESSAGE.format(location=key),
            "conflict": {"detected": False, "details": [], "message": None},
            "_error": repr(last_error),
        }

    cached = _cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    return {
        "reliable": False,
        "location": key,
        "cached": False,
        "as_of": None,
        "days": [],
        "message": NO_FORECAST_MESSAGE,
        "conflict": {"detected": False, "details": [], "message": None},
        "_error": repr(last_error),
    }


@guarded
def assess_spray_conditions(location: str, days_ahead: int = 0) -> dict[str, Any]:
    """Judge whether conditions suit a planned spray treatment on a given day.

    Call this for spray-timing questions instead of reading raw forecast
    values yourself. It fetches the forecast internally and applies fixed
    thresholds (rain wash-off and wind drift risk).

    :param location: Farmer's location.
    :param days_ahead: 0 = today, 1 = tomorrow, and so on.
    :return: {"verdict": "suitable" | "not suitable" | "cannot determine",
        "reason": str, "conditions": the forecast day's data when available}.
        Relay the reason to the farmer; never invent conditions that are
        not in `reason` or `conditions`.
    """
    forecast = get_forecast(location, days=days_ahead + 1)
    if not forecast["reliable"]:
        return {"verdict": "cannot determine", "reason": NO_FORECAST_MESSAGE, "conditions": None}
    if not location.strip():
        return {"verdict": "cannot determine", "reason": CANNOT_DETERMINE_MESSAGE, "conditions": None}

    day = forecast["days"][min(days_ahead, len(forecast["days"]) - 1)]

    if day["rain_probability"] > SPRAY_MAX_RAIN_PROBABILITY or day["rain_mm"] > SPRAY_MAX_RAIN_MM:
        return {
            "verdict": "not suitable",
            "reason": (
                f"Rain is likely ({int(round(day['rain_probability'] * 100))}% chance, "
                f"{day['rain_mm']} mm expected), which would wash the treatment off before it works."
            ),
            "conditions": day,
        }
    if day["wind_kmh"] > SPRAY_MAX_WIND_KMH:
        return {
            "verdict": "not suitable",
            "reason": (
                f"Wind is too strong ({day['wind_kmh']} km/h); the spray would drift away "
                "instead of landing on the plants."
            ),
            "conditions": day,
        }
    return {
        "verdict": "suitable",
        "reason": (
            f"Low rain risk ({int(round(day['rain_probability'] * 100))}% chance) and light wind "
            f"({day['wind_kmh']} km/h) — good conditions to spray."
        ),
        "conditions": day,
    }
