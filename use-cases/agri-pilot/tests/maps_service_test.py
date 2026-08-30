"""Tests for OSRM/Haversine route estimation."""

from unittest.mock import MagicMock, patch

from marketplace.maps_service import estimate_route


def test_estimate_route_haversine_when_osrm_fails():
    with patch("marketplace.maps_service._try_osrm", return_value=None):
        result = estimate_route(7.29, 80.63, 7.30, 80.64)
    assert result.source == "haversine"
    assert result.available is False
    assert result.distance_m > 0
    assert result.duration_s > 0


def test_estimate_route_uses_osrm_when_available():
    from marketplace.maps_service import RouteEstimate

    mock = RouteEstimate(distance_m=5000, duration_s=600, polyline="abc", available=True, source="osrm")
    with patch("marketplace.maps_service._try_osrm", return_value=mock):
        result = estimate_route(7.29, 80.63, 7.30, 80.64)
    assert result.source == "osrm"
    assert result.available is True
    assert result.distance_m == 5000


def test_try_osrm_parses_response():
    from marketplace.maps_service import _try_osrm

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "code": "Ok",
        "routes": [{"distance": 4200.5, "duration": 512.3, "geometry": "encoded"}],
    }
    mock_resp.raise_for_status = MagicMock()
    with patch("marketplace.maps_service.httpx.get", return_value=mock_resp):
        result = _try_osrm(7.29, 80.63, 7.30, 80.64)
    assert result is not None
    assert result.source == "osrm"
    assert result.distance_m == 4200
    assert result.duration_s == 512
