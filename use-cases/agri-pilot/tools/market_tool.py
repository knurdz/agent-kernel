"""Market price tools for AgriPilot (Increment 6.1).

`get_price` is the single source of price data for the market agent. It
currently returns deterministic mock data from an in-code catalog; Increment
11 swaps the fetch core for a live API behind the exact same return shape,
so the schema below is a contract — do not change it casually:

    {
        "reliable": True,
        "crop": "tomato",            # normalized (lowercase)
        "location": "kandy",         # normalized (lowercase) farmer location
        "as_of": "2026-08-22T10:30:00",  # when the data was fetched
        "data_freshness": "current",     # "current" | "stale" | None
        "options": [                     # one entry per wholesale market
            {
                "market": "dambulla",
                "price_per_kg": 92.5,
                # present only when quantity_kg was supplied:
                "estimated_revenue": 46250.0,
            },
            ...
        ],
        "message": None,             # farmer-facing limitation message
    }

Failure envelope (`reliable=False`): unknown crop or missing location —
`options=[]`, `as_of=None`, `data_freshness=None`, and a `message`
explaining the limitation. Never fabricate numbers to fill the gap.

Revenue estimate formula (computed by this tool only when `quantity_kg` is
supplied):

    estimated_revenue = round(price_per_kg * quantity_kg, 2)

Staleness rule: `data_freshness` is `"stale"` iff the data is older than
`STALE_AFTER_HOURS`. A stale result must never be quoted as current prices;
relay the `as_of` timestamp instead.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any, Callable, Optional

STALE_AFTER_HOURS = 24

# Wholesale markets the mock knows about. The farmer's location is recorded
# in the envelope for context but does not change national wholesale prices.
_MOCK_MARKETS = ("dambulla", "pettah", "keppetipola")

# Base price ranges (LKR per kg) per supported crop. Anything outside this
# catalog is an unknown crop: get_price returns reliable=False instead of
# inventing data.
_MOCK_CATALOG: dict[str, tuple[float, float]] = {
    "tomato": (40.0, 120.0),
    "onion": (60.0, 160.0),
    "potato": (80.0, 190.0),
}

NEED_CROP_MESSAGE = "I need to know which crop you want to sell before I can check market prices."

NEED_LOCATION_MESSAGE = "I need your location (nearest town) to find the markets you could sell at."

NO_PRICE_DATA_MESSAGE = (
    "I don't have market price data for {crop} right now, so I cannot advise " "on selling it. Please try again later."
)

_fetch_prices: Callable[[str, str], dict[str, Any]] = None  # type: ignore[assignment]
_now: Callable[[], datetime] = datetime.now  # injectable clock for tests


def _key(value: Optional[str]) -> str:
    """Normalize a free-text crop/location to a stable catalog key.

    Falls back to a naive de-pluralization ("tomatoes" -> "tomato") so
    farmer phrasing still matches the catalog; unknown crops stay unknown.
    """
    key = value.strip().lower() if isinstance(value, str) else ""
    if key not in _MOCK_CATALOG:
        if key.endswith("ies"):
            key = key[:-3] + "y"
        elif key.endswith("es") and key[:-2] in _MOCK_CATALOG:
            key = key[:-2]
        elif key.endswith("s") and key[:-1] in _MOCK_CATALOG:
            key = key[:-1]
    return key


def _mock_prices(crop_key: str, _location_key: str) -> dict[str, Any]:
    """Deterministic mock data: same crop+market always yields the same price.

    Seeded from a sha256 of crop+market so results are stable across
    processes (unlike the salted built-in hash). The location is unused:
    wholesale prices do not depend on where the farmer lives.
    """
    low, high = _MOCK_CATALOG[crop_key]
    options = []
    for market in _MOCK_MARKETS:
        seed = int.from_bytes(hashlib.sha256(f"{crop_key}:{market}".encode()).digest()[:4], "big")
        rng = random.Random(seed)
        options.append({"market": market, "price_per_kg": round(rng.uniform(low, high), 2)})
    return {"options": options, "as_of": datetime.now().isoformat(timespec="seconds")}


_fetch_prices = _mock_prices


def _no_data_envelope(crop: Optional[str], location: Optional[str], message: str) -> dict[str, Any]:
    return {
        "reliable": False,
        "crop": _key(crop) or None,
        "location": _key(location) or None,
        "as_of": None,
        "data_freshness": None,
        "options": [],
        "message": message,
    }


def _freshness(as_of: str) -> str:
    fetched = datetime.fromisoformat(as_of)
    age_hours = (_now() - fetched).total_seconds() / 3600.0
    return "stale" if age_hours > STALE_AFTER_HOURS else "current"


def _validate_quantity(quantity_kg: Any) -> float:
    if isinstance(quantity_kg, bool) or not isinstance(quantity_kg, (int, float)) or quantity_kg <= 0:
        raise ValueError("quantity_kg must be a positive number")
    return float(quantity_kg)


def get_price(crop: str, location: str = "", quantity_kg: Optional[float] = None) -> dict[str, Any]:
    """Return current wholesale price options for a crop.

    Call this with the farmer's crop before any selling advice, passing the
    harvest quantity as `quantity_kg` when known so each option carries an
    `estimated_revenue`. If `reliable` is false, relay `message` to the
    farmer and stop — NEVER state a price that did not come from this
    result's `options`. Before quoting any price check `data_freshness`: if
    it is `"stale"`, say the latest data is from `as_of` instead of quoting
    it as current.

    :param crop: Crop the farmer wants to sell (e.g. "tomato").
    :param location: Farmer's nearest town, used to pick relevant markets.
    :param quantity_kg: Harvest quantity in kilograms, if the farmer gave one.
    :return: The documented price envelope (see module docstring).
    :raises ValueError: If `quantity_kg` is given but not a positive number.
    """
    crop_key = _key(crop)
    location_key = _key(location)
    if not crop_key:
        return _no_data_envelope(crop, location, NEED_CROP_MESSAGE)
    if crop_key not in _MOCK_CATALOG:
        return _no_data_envelope(crop, location, NO_PRICE_DATA_MESSAGE.format(crop=crop_key))
    if not location_key:
        return _no_data_envelope(crop, location, NEED_LOCATION_MESSAGE)

    quantity = _validate_quantity(quantity_kg) if quantity_kg is not None else None

    fetched = _fetch_prices(crop_key, location_key)
    options = []
    for option in fetched["options"]:
        entry = {**option}
        if quantity is not None:
            entry["estimated_revenue"] = round(entry["price_per_kg"] * quantity, 2)
        options.append(entry)

    return {
        "reliable": True,
        "crop": crop_key,
        "location": location_key,
        "as_of": fetched["as_of"],
        "data_freshness": _freshness(fetched["as_of"]),
        "options": options,
        "message": None,
    }
