import 'dart:math' as math;

import 'package:latlong2/latlong.dart';

/// Decode an OSRM/Google encoded polyline string into map points.
List<LatLng> decodePolyline(String encoded) {
  final points = <LatLng>[];
  var index = 0;
  var lat = 0;
  var lng = 0;

  while (index < encoded.length) {
    var shift = 0;
    var result = 0;
    int byte;
    do {
      byte = encoded.codeUnitAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    final deltaLat = (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
    lat += deltaLat;

    shift = 0;
    result = 0;
    do {
      byte = encoded.codeUnitAt(index++) - 63;
      result |= (byte & 0x1f) << shift;
      shift += 5;
    } while (byte >= 0x20);
    final deltaLng = (result & 1) != 0 ? ~(result >> 1) : (result >> 1);
    lng += deltaLng;

    points.add(LatLng(lat / 1e5, lng / 1e5));
  }
  return points;
}

/// Approximate zoom to fit a set of points.
double zoomForPoints(List<LatLng> points, {double paddingFactor = 1.4}) {
  if (points.isEmpty) return 13;
  if (points.length == 1) return 15;
  var minLat = points.first.latitude;
  var maxLat = points.first.latitude;
  var minLon = points.first.longitude;
  var maxLon = points.first.longitude;
  for (final p in points) {
    minLat = math.min(minLat, p.latitude);
    maxLat = math.max(maxLat, p.latitude);
    minLon = math.min(minLon, p.longitude);
    maxLon = math.max(maxLon, p.longitude);
  }
  final latSpan = (maxLat - minLat).abs() * paddingFactor;
  final lonSpan = (maxLon - minLon).abs() * paddingFactor;
  final span = math.max(latSpan, lonSpan);
  if (span <= 0.0001) return 16;
  return (math.log(360 / span) / math.ln2).clamp(5.0, 18.0);
}

LatLng centerForPoints(List<LatLng> points) {
  if (points.isEmpty) return const LatLng(7.2906, 80.6337);
  var lat = 0.0;
  var lon = 0.0;
  for (final p in points) {
    lat += p.latitude;
    lon += p.longitude;
  }
  return LatLng(lat / points.length, lon / points.length);
}
