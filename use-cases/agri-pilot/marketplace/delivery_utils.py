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


def new_idempotency_token() -> str:
    return secrets.token_hex(8)
