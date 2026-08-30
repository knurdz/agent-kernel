import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/location/rider_location_tracker.dart';
import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
import '../../auth/providers/auth_provider.dart';
import '../data/delivery_repository.dart';

class RiderJobsScreen extends ConsumerStatefulWidget {
  const RiderJobsScreen({super.key});

  @override
  ConsumerState<RiderJobsScreen> createState() => _RiderJobsScreenState();
}

class _RiderJobsScreenState extends ConsumerState<RiderJobsScreen> {
  var _online = false;
  var _loading = true;
  var _jobs = <dynamic>[];
  RiderLocationTracker? _tracker;

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _tracker?.stop();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    final user = ref.read(authControllerProvider).asData?.value;
    setState(() => _online = user?.profile?.isOnline ?? false);
    await _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      if (_online) {
        final pos = await Geolocator.getCurrentPosition();
        await ref.read(deliveryRepositoryProvider).postLocation(pos.latitude, pos.longitude, accuracy: pos.accuracy);
      }
      final jobs = await ref.read(deliveryRepositoryProvider).availableJobs();
      if (mounted) setState(() => _jobs = jobs);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _toggleOnline(bool v) async {
    try {
      await ref.read(deliveryRepositoryProvider).setOnline(v);
      setState(() => _online = v);
      if (v) {
        _tracker = RiderLocationTracker(
          onLocation: (lat, lon, heading, accuracy) =>
              ref.read(deliveryRepositoryProvider).postLocation(lat, lon, heading: heading, accuracy: accuracy),
        );
        await _tracker!.start();
      } else {
        await _tracker?.stop();
      }
      await _refresh();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  Future<void> _accept(int orderId) async {
    try {
      await ref.read(deliveryRepositoryProvider).acceptJob(orderId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Job accepted')));
        await _refresh();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    }
  }

  Future<void> _reject(int orderId) async {
    await ref.read(deliveryRepositoryProvider).rejectJob(orderId);
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Available jobs'),
        actions: [
          Switch(value: _online, onChanged: _toggleOnline),
          const Padding(padding: EdgeInsets.only(right: 8), child: Text('Online')),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _refresh,
              child: _jobs.isEmpty
                  ? ListView(children: const [SizedBox(height: 120, child: Center(child: Text('No jobs nearby')))])
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _jobs.length,
                      itemBuilder: (_, i) {
                        final j = _jobs[i];
                        return Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('${j.crop} · ${j.quantityKg.toStringAsFixed(0)} kg',
                                    style: Theme.of(context).textTheme.titleMedium),
                                Text('Pickup: ${j.pickupDistrictArea}'),
                                Text('Deliver: ${j.deliveryDistrictArea}'),
                                Text('${j.distanceToPickupKm.toStringAsFixed(1)} km to pickup · ~${(j.routeDurationS / 60).round()} min route'),
                                const SizedBox(height: 12),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.end,
                                  children: [
                                    TextButton(onPressed: () => _reject(j.orderId as int), child: const Text('Reject')),
                                    const SizedBox(width: 8),
                                    FilledButton(onPressed: () => _accept(j.orderId as int), child: const Text('Accept')),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}

class RiderActiveDeliveryScreen extends ConsumerStatefulWidget {
  const RiderActiveDeliveryScreen({super.key});

  @override
  ConsumerState<RiderActiveDeliveryScreen> createState() => _RiderActiveDeliveryScreenState();
}

class _RiderActiveDeliveryScreenState extends ConsumerState<RiderActiveDeliveryScreen> {
  Map<String, dynamic>? _active;
  var _loading = true;
  final _pinCtrl = TextEditingController();
  RiderLocationTracker? _tracker;

  @override
  void initState() {
    super.initState();
    _load();
    _tracker = RiderLocationTracker(
      onLocation: (lat, lon, heading, accuracy) =>
          ref.read(deliveryRepositoryProvider).postLocation(lat, lon, heading: heading, accuracy: accuracy),
    );
    _tracker!.start();
  }

  @override
  void dispose() {
    _tracker?.stop();
    _pinCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final d = await ref.read(deliveryRepositoryProvider).activeDelivery();
      if (mounted) setState(() => _active = d);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _advance(String status) async {
    final id = _active?['delivery_id'] as int?;
    if (id == null) return;
    await ref.read(deliveryRepositoryProvider).updateDeliveryStatus(id, status);
    await _load();
  }

  Future<void> _complete() async {
    final orderId = _active?['order_id'] as int?;
    if (orderId == null) return;
    await ref.read(deliveryRepositoryProvider).confirmHandoffRider(orderId, _pinCtrl.text.trim());
    await _load();
  }

  LatLng? _ll(Map<String, dynamic>? m, String prefix) {
    final lat = m?['${prefix}_latitude'] ?? m?['latitude'];
    final lon = m?['${prefix}_longitude'] ?? m?['longitude'];
    if (lat == null || lon == null) return null;
    return LatLng((lat as num).toDouble(), (lon as num).toDouble());
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    if (_active == null) {
      return const Scaffold(body: Center(child: Text('No active delivery')));
    }
    final pickup = _ll(_active!['pickup'] as Map<String, dynamic>?, '');
    final delivery = _ll(_active!['delivery'] as Map<String, dynamic>?, '');
    final status = _active!['status'] as String? ?? '';

    return Scaffold(
      appBar: AppBar(title: const Text('Active delivery'), actions: [StatusChip(status: status)]),
      body: Column(
        children: [
          SizedBox(height: 220, child: DeliveryTrackingMap(pickup: pickup, delivery: delivery)),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (status == 'assigned')
                  FilledButton(onPressed: () => _advance('en_route_pickup'), child: const Text('Start to pickup')),
                if (status == 'en_route_pickup')
                  FilledButton(onPressed: () => _advance('arrived_pickup'), child: const Text('Arrived at pickup')),
                if (status == 'arrived_pickup')
                  FilledButton(onPressed: () => _advance('picked_up'), child: const Text('Picked up')),
                if (status == 'picked_up')
                  FilledButton(onPressed: () => _advance('in_transit'), child: const Text('In transit to buyer')),
                if (status == 'in_transit') ...[
                  TextField(controller: _pinCtrl, decoration: const InputDecoration(labelText: 'Buyer PIN')),
                  FilledButton(onPressed: _complete, child: const Text('Confirm delivery')),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
