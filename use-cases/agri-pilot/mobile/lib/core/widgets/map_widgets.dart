import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../maps/polyline_utils.dart';
import '../theme/app_theme.dart';

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
                      width: 48,
                      height: 48,
                      child: _MapPinBadge(
                        color: Theme.of(context).colorScheme.error,
                        icon: Icons.location_on,
                        size: 44,
                      ),
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

/// Circular map pin with white border and drop shadow.
class _MapPinBadge extends StatelessWidget {
  const _MapPinBadge({
    required this.color,
    required this.icon,
    this.size = 40,
  });

  final Color color;
  final IconData icon;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.22),
            blurRadius: 8,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Icon(icon, color: Colors.white, size: size * 0.5),
    );
  }
}

/// Rider navigation puck with heading arrow.
class _RiderPuck extends StatelessWidget {
  const _RiderPuck({this.heading});

  final double? heading;

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 52,
          height: 52,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF1565C0).withValues(alpha: 0.18),
          ),
        ),
        Transform.rotate(
          angle: (heading ?? 0) * 3.1415926535 / 180,
          child: Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: const Color(0xFF1565C0),
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 3),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.25),
                  blurRadius: 10,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: const Icon(Icons.navigation, color: Colors.white, size: 22),
          ),
        ),
      ],
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
    this.showControls = true,
    this.onOpenMaps,
  });

  final LatLng? pickup;
  final LatLng? delivery;
  final LatLng? rider;
  final List<LatLng>? polylinePoints;
  final double? riderHeading;
  final bool followRider;
  final bool showControls;
  final VoidCallback? onOpenMaps;

  @override
  State<DeliveryTrackingMap> createState() => DeliveryTrackingMapState();
}

class DeliveryTrackingMapState extends State<DeliveryTrackingMap> {
  final _mapController = MapController();
  List<LatLng>? _lastFitPoints;

  MapController get mapController => _mapController;

  @override
  void dispose() {
    _mapController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant DeliveryTrackingMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.followRider && widget.rider != null) {
      _followRider();
    }
  }

  void fitRoute() {
    final points = _allPoints();
    if (points.isEmpty) return;
    _lastFitPoints = List.of(points);
    final center = centerForPoints(points);
    final zoom = zoomForPoints(points);
    _mapController.move(center, zoom);
  }

  void _followRider() {
    if (widget.rider != null) {
      _mapController.move(widget.rider!, _mapController.camera.zoom.clamp(5.0, 18.0));
    }
  }

  void _maybeRecenter() {
    final points = _allPoints();
    if (points.isEmpty) return;
    if (widget.followRider && widget.rider != null) {
      _followRider();
      return;
    }
    if (_pointsChanged(points)) {
      fitRoute();
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
    if (widget.polylinePoints != null && widget.polylinePoints!.length >= 2) {
      pts.addAll(widget.polylinePoints!);
    }
    return pts;
  }

  @override
  Widget build(BuildContext context) {
    final points = _allPoints();
    final center = widget.rider ?? widget.pickup ?? widget.delivery ?? defaultMapCenter();
    final zoom = points.length >= 2 ? zoomForPoints(points) : 14.0;
    final primary = Theme.of(context).colorScheme.primary;

    WidgetsBinding.instance.addPostFrameCallback((_) => _maybeRecenter());

    final markers = <Marker>[];
    if (widget.pickup != null) {
      markers.add(
        Marker(
          point: widget.pickup!,
          width: 48,
          height: 48,
          child: const _MapPinBadge(color: AppColors.primary, icon: Icons.storefront, size: 44),
        ),
      );
    }
    if (widget.delivery != null) {
      markers.add(
        Marker(
          point: widget.delivery!,
          width: 48,
          height: 48,
          child: const _MapPinBadge(color: AppColors.secondary, icon: Icons.home, size: 44),
        ),
      );
    }
    if (widget.rider != null) {
      markers.add(
        Marker(
          point: widget.rider!,
          width: 56,
          height: 56,
          child: _RiderPuck(heading: widget.riderHeading),
        ),
      );
    }

    return Stack(
      children: [
        FlutterMap(
          mapController: _mapController,
          options: MapOptions(initialCenter: center, initialZoom: zoom, minZoom: 5, maxZoom: 18),
          children: [
            TileLayer(
              urlTemplate: _osmTileUrl,
              userAgentPackageName: 'com.example.mobile',
            ),
            if (widget.polylinePoints != null && widget.polylinePoints!.length >= 2) ...[
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: widget.polylinePoints!,
                    color: Colors.white,
                    strokeWidth: 8,
                  ),
                ],
              ),
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: widget.polylinePoints!,
                    color: primary,
                    strokeWidth: 5,
                  ),
                ],
              ),
            ],
            MarkerLayer(markers: markers),
          ],
        ),
        if (widget.showControls)
          Positioned(
            right: 12,
            bottom: 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                _MapControlButton(
                  icon: Icons.center_focus_strong,
                  tooltip: 'Fit route',
                  onPressed: fitRoute,
                ),
                if (widget.onOpenMaps != null) ...[
                  const SizedBox(height: 8),
                  _MapControlButton(
                    icon: Icons.directions,
                    tooltip: 'Open in Maps',
                    onPressed: widget.onOpenMaps!,
                  ),
                ],
              ],
            ),
          ),
      ],
    );
  }
}

class _MapControlButton extends StatelessWidget {
  const _MapControlButton({
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      elevation: 3,
      shadowColor: Colors.black26,
      borderRadius: BorderRadius.circular(12),
      color: Theme.of(context).colorScheme.surfaceContainerLowest,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(12),
        child: Tooltip(
          message: tooltip,
          child: SizedBox(
            width: 44,
            height: 44,
            child: Icon(icon, size: 22, color: Theme.of(context).colorScheme.primary),
          ),
        ),
      ),
    );
  }
}
