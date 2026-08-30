import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

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

/// Read-only tracking map with pickup, delivery, and rider markers.
class DeliveryTrackingMap extends StatelessWidget {
  const DeliveryTrackingMap({
    super.key,
    required this.pickup,
    this.delivery,
    this.rider,
    this.polylinePoints,
  });

  final LatLng? pickup;
  final LatLng? delivery;
  final LatLng? rider;
  final List<LatLng>? polylinePoints;

  @override
  Widget build(BuildContext context) {
    final center = rider ?? pickup ?? delivery ?? defaultMapCenter();
    final markers = <Marker>[];

    if (pickup != null) {
      markers.add(_marker(pickup!, Colors.green, 'Pickup'));
    }
    if (delivery != null) {
      markers.add(_marker(delivery!, Colors.orange, 'Delivery'));
    }
    if (rider != null) {
      markers.add(_marker(rider!, Colors.blue, 'Rider'));
    }

    return FlutterMap(
      options: MapOptions(initialCenter: center, initialZoom: 13),
      children: [
        TileLayer(
          urlTemplate: _osmTileUrl,
          userAgentPackageName: 'com.example.mobile',
        ),
        if (polylinePoints != null && polylinePoints!.length >= 2)
          PolylineLayer(
            polylines: [
              Polyline(
                points: polylinePoints!,
                color: Colors.green,
                strokeWidth: 4,
              ),
            ],
          ),
        MarkerLayer(markers: markers),
      ],
    );
  }

  Marker _marker(LatLng point, Color color, String label) {
    return Marker(
      point: point,
      width: 36,
      height: 36,
      child: Tooltip(
        message: label,
        child: Icon(Icons.location_on, color: color, size: 36),
      ),
    );
  }
}
