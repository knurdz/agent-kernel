import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
import '../data/delivery_repository.dart';

class OrderTrackingScreen extends ConsumerStatefulWidget {
  const OrderTrackingScreen({super.key, required this.orderId});

  final int orderId;

  @override
  ConsumerState<OrderTrackingScreen> createState() => _OrderTrackingScreenState();
}

class _OrderTrackingScreenState extends ConsumerState<OrderTrackingScreen> {
  Timer? _poll;
  var _loading = true;
  dynamic _tracking;
  final _pinCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _load(silent: true));
  }

  @override
  void dispose() {
    _poll?.cancel();
    _pinCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final t = await ref.read(deliveryRepositoryProvider).tracking(widget.orderId);
      if (mounted) setState(() => _tracking = t);
    } finally {
      if (mounted && !silent) setState(() => _loading = false);
    }
  }

  LatLng? _latLng(Map<String, dynamic>? m) {
    if (m == null) return null;
    final lat = m['latitude'];
    final lon = m['longitude'];
    if (lat == null || lon == null) return null;
    return LatLng((lat as num).toDouble(), (lon as num).toDouble());
  }

  Future<void> _confirmHandoff() async {
    try {
      await ref.read(deliveryRepositoryProvider).confirmHandoffBuyer(widget.orderId, _pinCtrl.text.trim());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Handoff confirmed')));
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _tracking == null) {
      return Scaffold(appBar: AppBar(title: const Text('Track order')), body: const Center(child: CircularProgressIndicator()));
    }
    final t = _tracking;
    if (t == null) {
      return Scaffold(appBar: AppBar(title: const Text('Track order')), body: const Center(child: Text('Not found')));
    }
    final pickup = _latLng(t.pickup as Map<String, dynamic>?);
    final delivery = _latLng(t.delivery as Map<String, dynamic>?);
    final rider = _latLng(t.rider as Map<String, dynamic>?);
    final stale = t.rider['stale'] == true;

    return Scaffold(
      appBar: AppBar(
        title: Text('${t.crop} order'),
        actions: [StatusChip(status: t.status as String)],
      ),
      body: Column(
        children: [
          SizedBox(
            height: 260,
            child: DeliveryTrackingMap(pickup: pickup, delivery: delivery, rider: rider),
          ),
          if (stale && rider != null)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text('Rider location may be stale', style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Text('${t.quantityKg} kg · ${t.fulfillmentMode}'),
                const SizedBox(height: 8),
                ...((t.events as List<Map<String, dynamic>>?) ?? []).map(
                  (e) => ListTile(
                    dense: true,
                    title: Text(e['event_type'] as String? ?? ''),
                    subtitle: Text(e['created_at'] as String? ?? ''),
                  ),
                ),
                if (['ready', 'in_transit', 'picked_up'].contains(t.status)) ...[
                  const SizedBox(height: 16),
                  TextField(
                    controller: _pinCtrl,
                    decoration: const InputDecoration(labelText: 'Handoff PIN', border: OutlineInputBorder()),
                  ),
                  const SizedBox(height: 8),
                  FilledButton(onPressed: _confirmHandoff, child: const Text('Confirm received')),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
