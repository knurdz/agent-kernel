import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

/// Streams rider GPS to a callback while active delivery tracking is enabled.
class RiderLocationTracker {
  RiderLocationTracker({required this.onLocation});

  final Future<void> Function(double lat, double lon, double? heading, double? accuracy) onLocation;
  StreamSubscription<Position>? _sub;
  var _running = false;

  Future<bool> ensurePermission() async {
    var perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      perm = await Geolocator.requestPermission();
    }
    if (perm == LocationPermission.deniedForever || perm == LocationPermission.denied) {
      return false;
    }
    return true;
  }

  Future<void> start() async {
    if (_running) return;
    if (!await ensurePermission()) return;
    _running = true;
    const settings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 15,
    );
    _sub = Geolocator.getPositionStream(locationSettings: settings).listen((pos) async {
      try {
        await onLocation(pos.latitude, pos.longitude, pos.heading, pos.accuracy);
      } catch (_) {
        // best-effort
      }
    });
  }

  Future<void> stop() async {
    _running = false;
    await _sub?.cancel();
    _sub = null;
  }
}
