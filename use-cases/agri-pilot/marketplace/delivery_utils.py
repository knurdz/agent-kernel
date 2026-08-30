"""Shared helpers for rider delivery MVP."""

from __future__ import annotations

import math
import os
import random
import secrets
from typing import Optional

from passlib.context import CryptContext

_pin_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def bounding_box(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Return min_lat, max_lat, min_lon, max_lon for a square bounding box."""
    lat_delta = radius_km / 111.0
    cos_lat = max(math.cos(math.radians(lat)), 0.01)
    lon_delta = radius_km / (111.0 * cos_lat)
    return lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta


def get_dispatch_radius_km() -> float:
    env = os.environ.get("AK_DELIVERY__DISPATCH_RADIUS_KM", "").strip()
    if env:
        try:
            return max(float(env), 1.0)
        except ValueError:
            pass
    try:
        import yaml

        with open("config.yaml", "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        val = (data.get("delivery") or {}).get("dispatch_radius_km")
        if isinstance(val, (int, float)) and val > 0:
            return float(val)
    except Exception:
        pass
    return 25.0


def get_location_stale_seconds() -> int:
    env = os.environ.get("AK_DELIVERY__LOCATION_STALE_SECONDS", "").strip()
    if env and env.isdigit():
        return max(int(env), 30)
    return 120


def get_min_location_interval_seconds() -> int:
    env = os.environ.get("AK_DELIVERY__MIN_LOCATION_INTERVAL_SECONDS", "").strip()
    if env and env.isdigit():
        return max(int(env), 3)
    return 5


def generate_handoff_pin() -> str:
    return f"{random.randint(0, 9999):04d}"


def hash_handoff_pin(pin: str) -> str:
    return _pin_ctx.hash(pin)


def verify_handoff_pin(pin: str, pin_hash: str) -> bool:
    return _pin_ctx.verify(pin, pin_hash)


def valid_coordinate(lat: Optional[float], lon: Optional[float]) -> bool:
    if lat is None or lon is None:
        return False
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


# Approximate district centroids for Sri Lanka (no live geocoding in production).
_DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "kandy": (7.2906, 80.6337),
    "matale": (7.4675, 80.6234),
    "nuwara eliya": (6.9497, 80.7891),
    "galle": (6.0535, 80.2210),
    "matara": (5.9549, 80.5550),
    "colombo": (6.9271, 79.8612),
    "gampaha": (7.0917, 79.9990),
}


def geocode_district_centroid(district: Optional[str]) -> Optional[tuple[float, float]]:
    """Return approximate lat/lon for a Sri Lanka district name, or None."""
    if not district or not district.strip():
        return None
    return _DISTRICT_CENTROIDS.get(district.strip().lower())


def resolve_farmer_pickup(
    farmer_profile,
    *,
    override_lat: Optional[float] = None,
    override_lon: Optional[float] = None,
    override_label: Optional[str] = None,
) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """Resolve farm pickup coordinates: explicit pin, profile GPS, then district centroid."""
    if valid_coordinate(override_lat, override_lon):
        return override_lat, override_lon, override_label

    if farmer_profile is not None and valid_coordinate(farmer_profile.latitude, farmer_profile.longitude):
        label = farmer_profile.address_label
        if not label and farmer_profile.district:
            label = f"{farmer_profile.district}, Sri Lanka"
        return farmer_profile.latitude, farmer_profile.longitude, label

    if farmer_profile is not None and farmer_profile.district:
        coords = geocode_district_centroid(farmer_profile.district)
        if coords:
            label = farmer_profile.address_label or f"{farmer_profile.district}, Sri Lanka"
            return coords[0], coords[1], label

    return None, None, None


def new_idempotency_token() -> str:
    return secrets.token_hex(8)
