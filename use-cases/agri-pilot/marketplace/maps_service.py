"""Route estimates via public OSRM (optional) or Haversine fallback — no API keys."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger("agripilot.marketplace.maps")

OSRM_BASE_URL = os.environ.get(
    "AK_DELIVERY__OSRM_BASE_URL",
    "https://router.project-osrm.org",
).rstrip("/")
OSRM_TIMEOUT_SECONDS = 8.0
OSRM_USER_AGENT = "AgriPilot/1.0 (delivery-mvp; contact=dev@localhost)"


@dataclass
class RouteEstimate:
    distance_m: int
    duration_s: int
    polyline: Optional[str] = None
    available: bool = True
    source: str = "haversine"


def _haversine_estimate(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> RouteEstimate:
    from marketplace.delivery_utils import haversine_km

    km = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
    return RouteEstimate(
        distance_m=int(km * 1000),
        duration_s=int(km / 30.0 * 3600),  # assume 30 km/h average
        polyline=None,
        available=False,
        source="haversine",
    )


def _try_osrm(origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float) -> Optional[RouteEstimate]:
    """Query public OSRM demo server; returns None on failure."""
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        f"?overview=full&geometries=polyline"
    )
    try:
        resp = httpx.get(
            url,
            timeout=OSRM_TIMEOUT_SECONDS,
            headers={"User-Agent": OSRM_USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            return None
        routes = data.get("routes") or []
        if not routes:
            return None
        route = routes[0]
        distance_m = int(route.get("distance") or 0)
        duration_s = int(route.get("duration") or 0)
        geometry = route.get("geometry") or ""
        return RouteEstimate(
            distance_m=distance_m,
            duration_s=duration_s,
            polyline=geometry if geometry else None,
            available=True,
            source="osrm",
        )
    except Exception as exc:  # noqa: BLE001
        log.debug("osrm route failed: %s", exc)
        return None


def estimate_route(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> RouteEstimate:
    """Return route distance/duration via OSRM when reachable, else Haversine."""
    osrm = _try_osrm(origin_lat, origin_lon, dest_lat, dest_lon)
    if osrm is not None:
        return osrm
    log.info("using haversine fallback for route estimate")
    return _haversine_estimate(origin_lat, origin_lon, dest_lat, dest_lon)
