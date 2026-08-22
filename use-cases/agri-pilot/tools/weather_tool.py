"""Weather tools for AgriPilot (Increment 5.1).

`get_forecast` is the single source of forecast data for the resource
agent. It currently returns deterministic mock data; Increment 11.1 swaps
the fetch core for a live API behind the exact same return shape, so the
schema below is a contract — do not change it casually:

    {
        "reliable": True,
        "location": "kandy",          # normalized (lowercase) location
        "cached": False,              # True when served from the fallback cache
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
    }

On repeated fetch failure the tool never invents numbers: it falls back to
the last cached forecast for that location (`reliable=True, cached=True`),
or reports `reliable=False` with a limitation `message` (Increment 5.4).
"""

from __future__ import annotations

import hashlib
import random
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

FORECAST_DAYS_DEFAULT = 3
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

SPRAY_MAX_RAIN_PROBABILITY = 0.3
SPRAY_MAX_RAIN_MM = 2.0
SPRAY_MAX_WIND_KMH = 15.0

NO_FORECAST_MESSAGE = (
    "I could not get a reliable weather forecast for your area right now, "
    "so I cannot advise on this. Please try again later."
)

CANNOT_DETERMINE_MESSAGE = "I need your location to check the weather conditions before I can " "advise on spraying."

_fetcher: Callable[[str, int], dict[str, list[dict[str, Any]]]] = None  # type: ignore[assignment]
_sleep: Callable[[float], None] = time.sleep

_cache: dict[str, dict[str, Any]] = {}


def _location_key(location: str) -> str:
    """Normalize a free-text location to a stable cache/seed key."""
    return location.strip().lower()


def _mock_forecast(location: str, days: int) -> dict[str, list[dict[str, Any]]]:
    """Deterministic mock data: same location always yields the same values.

    Seeded from a sha256 of the location so results are stable across
    processes (unlike the salted built-in hash).
    """
    seed = int.from_bytes(hashlib.sha256(location.encode()).digest()[:4], "big")
    rng = random.Random(seed)
    out = []
    for offset in range(days):
        day = date.today() + timedelta(days=offset)
        rain_probability = round(rng.uniform(0.05, 0.95), 2)
        out.append(
            {
                "date": day.isoformat(),
                "temp_min_c": round(rng.uniform(18.0, 24.0), 1),
                "temp_max_c": round(rng.uniform(28.0, 34.0), 1),
                "rain_probability": rain_probability,
                "rain_mm": round(rain_probability * rng.uniform(0.0, 25.0), 1),
                "wind_kmh": round(rng.uniform(2.0, 20.0), 1),
                "et0_mm": round(rng.uniform(3.0, 6.0), 1),
            }
        )
    return {"days": out}


def _fetch_forecast(location: str, days: int) -> dict[str, list[dict[str, Any]]]:
    """Fetch core, separated from retry/cache so tests can inject failures.

    Increment 11.1 replaces this body with a real API call returning the
    same shape.
    """
    return _mock_forecast(location, days)


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
    last_error: Optional[Exception] = None
    for attempt in range(RETRY_ATTEMPTS):
        try:
            fetched = _fetch_forecast(key, days)
            result: dict[str, Any] = {
                "reliable": True,
                "location": key,
                "cached": False,
                "as_of": datetime.now().isoformat(timespec="seconds"),
                **fetched,
                "message": None,
            }
            _cache[key] = result
            return result
        except Exception as exc:  # noqa: BLE001 - any fetch failure triggers retry/fallback
            last_error = exc
            if attempt < RETRY_ATTEMPTS - 1:
                _sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))

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
        "_error": repr(last_error),
    }


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
