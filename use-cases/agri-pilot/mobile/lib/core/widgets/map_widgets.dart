import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../maps/polyline_utils.dart';

/// OpenStreetMap tile URL (no API key required).
const _osmTileUrl = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/// Default map center: Kandy, Sri Lanka.
LatLng defaultMapCenter() => const LatLng(7.2906, 80.6337);

/// Tap-to-select map pin picker (OpenStreetMap).
class MapAddressPicker extends StatefulWidget {
  const MapAddressPicker({
    super.key,
    required this.initialPosition,
    required this.onConfirmed,
    this.title = 'Select location',
  });

  final LatLng initialPosition;
  final void Function(LatLng position, String label) onConfirmed;
  final String title;

  @override
  State<MapAddressPicker> createState() => _MapAddressPickerState();
}

class _MapAddressPickerState extends State<MapAddressPicker> {
  late LatLng _pin;
  final _labelCtrl = TextEditingController();
  final _mapController = MapController();

  @override
  void initState() {
    super.initState();
    _pin = widget.initialPosition;
    _labelCtrl.text = 'Selected pin';
  }

  @override
  void dispose() {
    _labelCtrl.dispose();
    _mapController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: Column(
        children: [
          Expanded(
            child: FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: _pin,
                initialZoom: 14,
                onTap: (_, point) => setState(() => _pin = point),
              ),
              children: [
                TileLayer(
                  urlTemplate: _osmTileUrl,
                  userAgentPackageName: 'com.example.mobile',
                ),
                MarkerLayer(
                  markers: [
                    Marker(
                      point: _pin,
                      width: 40,
                      height: 40,
                      child: const Icon(Icons.location_on, color: Colors.red, size: 40),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Lat ${_pin.latitude.toStringAsFixed(5)}, Lon ${_pin.longitude.toStringAsFixed(5)}',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
                const SizedBox(height: 8),
                TextField(
                  controller: _labelCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Address label',
                    border: OutlineInputBorder(),
                  ),
                ),
                const SizedBox(height: 12),
                FilledButton(
                  onPressed: () {
                    widget.onConfirmed(
                      _pin,
                      _labelCtrl.text.trim().isEmpty ? 'Selected pin' : _labelCtrl.text.trim(),
                    );
                    Navigator.of(context).pop();
                  },
                  child: const Text('Confirm location'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Live tracking map with pickup, delivery, rider markers and optional route polyline.
class DeliveryTrackingMap extends StatefulWidget {
  const DeliveryTrackingMap({
    super.key,
    required this.pickup,
    this.delivery,
    this.rider,
    this.polylinePoints,
    this.riderHeading,
    this.followRider = false,
  });

  final LatLng? pickup;
  final LatLng? delivery;
  final LatLng? rider;
  final List<LatLng>? polylinePoints;
  final double? riderHeading;
  final bool followRider;

  @override
  State<DeliveryTrackingMap> createState() => _DeliveryTrackingMapState();
}

class _DeliveryTrackingMapState extends State<DeliveryTrackingMap> {
  final _mapController = MapController();
  List<LatLng>? _lastFitPoints;

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant DeliveryTrackingMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    _maybeRecenter();
  }

  void _maybeRecenter() {
    final points = _allPoints();
    if (points.isEmpty) return;
    if (widget.followRider && widget.rider != null) {
      _mapController.move(widget.rider!, _mapController.camera.zoom);
      return;
    }
    if (_pointsChanged(points)) {
      _lastFitPoints = List.of(points);
      final center = centerForPoints(points);
      final zoom = zoomForPoints(points);
      _mapController.move(center, zoom);
    }
  }

  bool _pointsChanged(List<LatLng> points) {
    if (_lastFitPoints == null || _lastFitPoints!.length != points.length) return true;
    for (var i = 0; i < points.length; i++) {
      if (points[i].latitude != _lastFitPoints![i].latitude ||
          points[i].longitude != _lastFitPoints![i].longitude) {
        return true;
      }
    }
    return false;
  }

  List<LatLng> _allPoints() {
    final pts = <LatLng>[];
    if (widget.pickup != null) pts.add(widget.pickup!);
    if (widget.delivery != null) pts.add(widget.delivery!);
    if (widget.rider != null) pts.add(widget.rider!);
    if (widget.polylinePoints != null) pts.addAll(widget.polylinePoints!);
    return pts;
  }

  @override
  Widget build(BuildContext context) {
    final points = _allPoints();
    final center = widget.rider ?? widget.pickup ?? widget.delivery ?? defaultMapCenter();
    final zoom = points.length >= 2 ? zoomForPoints(points) : 14.0;

    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeRecenter());

    final markers = <Marker>[];
    if (widget.pickup != null) {
      markers.add(_marker(widget.pickup!, Colors.green, Icons.store, 'Farm pickup'));
    }
    if (widget.delivery != null) {
      markers.add(_marker(widget.delivery!, Colors.orange, Icons.home, 'Delivery'));
    }
    if (widget.rider != null) {
      markers.add(_riderMarker(widget.rider!, widget.riderHeading));
    }

    return FlutterMap(
      mapController: _mapController,
      options: MapOptions(initialCenter: center, initialZoom: zoom, minZoom: 5, maxZoom: 18),
      children: [
        TileLayer(
          urlTemplate: _osmTileUrl,
          userAgentPackageName: 'com.example.mobile',
        ),
        if (widget.polylinePoints != null && widget.polylinePoints!.length >= 2)
          PolylineLayer(
            polylines: [
              Polyline(
                points: widget.polylinePoints!,
                color: Theme.of(context).colorScheme.primary,
                strokeWidth: 4,
              ),
            ],
          ),
        MarkerLayer(markers: markers),
      ],
    );
  }

  Marker _marker(LatLng point, Color color, IconData icon, String label) {
    return Marker(
      point: point,
      width: 40,
      height: 40,
      child: Tooltip(
        message: label,
        child: Icon(icon, color: color, size: 36),
      ),
    );
  }

  Marker _riderMarker(LatLng point, double? heading) {
    return Marker(
      point: point,
      width: 44,
      height: 44,
      child: Transform.rotate(
        angle: (heading ?? 0) * 3.1415926535 / 180,
        child: const Icon(Icons.delivery_dining, color: Colors.blue, size: 40),
      ),
    );
  }
}
