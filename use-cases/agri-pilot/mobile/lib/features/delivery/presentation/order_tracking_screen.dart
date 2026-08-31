import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/location/rider_location_tracker.dart';
import '../../../core/maps/polyline_utils.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/storage/handoff_pin_store.dart';
import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
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
  OrderTracking? _tracking;
  OrderItem? _orderItem;
  final _pinCtrl = TextEditingController();
  RiderLocationTracker? _tracker;
  final _pinStore = HandoffPinStore();
  var _savedPinLoaded = false;

  @override
  void initState() {
    super.initState();
    _load();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _load(silent: true));
    _startRiderGpsIfNeeded();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _tracker?.stop();
    _pinCtrl.dispose();
    super.dispose();
  }

  Future<void> _startRiderGpsIfNeeded() async {
    final user = ref.read(authControllerProvider).asData?.value;
    if (user?.isRider != true) return;
    _tracker = RiderLocationTracker(
      onLocation: (lat, lon, heading, accuracy) =>
          ref.read(deliveryRepositoryProvider).postLocation(lat, lon, heading: heading, accuracy: accuracy),
    );
    await _tracker!.start();
  }

  Future<void> _load({bool silent = false}) async {
    if (!silent) setState(() => _loading = true);
    try {
      final repo = ref.read(deliveryRepositoryProvider);
      final t = await repo.tracking(widget.orderId);
      OrderItem? order;
      final user = ref.read(authControllerProvider).asData?.value;
      if (user?.isRider != true) {
        try {
          order = await repo.getOrder(widget.orderId);
        } catch (_) {}
      }
      if (mounted) {
        setState(() {
          _tracking = t;
          _orderItem = order;
        });
        if (!_savedPinLoaded) {
          _savedPinLoaded = true;
          final saved = await _pinStore.read(widget.orderId);
          if (saved != null && mounted) _pinCtrl.text = saved;
        }
      }
    } finally {
      if (mounted && !silent) setState(() => _loading = false);
    }
  }

  LatLng? _toLatLng(TrackingLocation loc) {
    if (!loc.hasCoordinates) return null;
    return LatLng(loc.latitude!, loc.longitude!);
  }

  LatLng? _riderLatLng(TrackingRider rider) {
    if (!rider.hasCoordinates) return null;
    return LatLng(rider.latitude!, rider.longitude!);
  }

  Future<void> _callPhone(String? phone) async {
    if (phone == null || phone.isEmpty) return;
    final uri = Uri.parse('tel:$phone');
    if (await canLaunchUrl(uri)) await launchUrl(uri);
  }

  Future<void> _openExternalMaps() async {
    final t = _tracking;
    if (t == null) return;
    LatLng? dest;
    if (t.nextStop == 'pickup') {
      dest = _toLatLng(t.pickup);
    } else if (t.nextStop == 'delivery') {
      dest = _toLatLng(t.delivery);
    }
    dest ??= _toLatLng(t.delivery) ?? _toLatLng(t.pickup);
    if (dest == null) return;
    final uri = Uri.parse(
      'https://www.google.com/maps/dir/?api=1&destination=${dest.latitude},${dest.longitude}&travelmode=driving',
    );
    if (await canLaunchUrl(uri)) await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  Future<void> _confirmHandoffBuyer() async {
    try {
      await ref.read(deliveryRepositoryProvider).confirmHandoffBuyer(widget.orderId, _pinCtrl.text.trim());
      await _pinStore.delete(widget.orderId);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Handoff confirmed')));
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
    }
  }

  Future<void> _confirmHandoffRider() async {
    try {
      await ref.read(deliveryRepositoryProvider).confirmHandoffRider(widget.orderId, _pinCtrl.text.trim());
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Delivery completed')));
        await _load();
      }
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
    }
  }

  Future<void> _advanceRider(String status) async {
    final deliveryId = _tracking?.deliveryId ?? _orderItem?.deliveryId;
    if (deliveryId == null) return;
    try {
      await ref.read(deliveryRepositoryProvider).updateDeliveryStatus(deliveryId, status);
      if (mounted && status == 'picked_up') {
        context.go('/orders/${widget.orderId}/track');
      }
      await _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
    }
  }

  Future<void> _farmerConfirm() async {
    final order = _orderItem;
    if (order == null) return;
    double? pickupLat;
    double? pickupLon;
    String? pickupLabel;

    final needsPin = order.fulfillmentMode == 'delivery' && !order.hasPickupCoordinates;
    if (needsPin) {
      LatLng? pin;
      await Navigator.of(context).push<void>(
        MaterialPageRoute(
          builder: (_) => MapAddressPicker(
            initialPosition: defaultMapCenter(),
            title: 'Pickup location',
            onConfirmed: (p, l) {
              pin = p;
              pickupLabel = l;
            },
          ),
        ),
      );
      if (pin == null) return;
      pickupLat = pin!.latitude;
      pickupLon = pin!.longitude;
    }

    try {
      await ref.read(deliveryRepositoryProvider).farmerConfirm(
            widget.orderId,
            quantityKg: order.quantityKg,
            pickupAddressLabel: pickupLabel ?? order.pickupAddressLabel,
            pickupLatitude: pickupLat ?? order.pickupLatitude,
            pickupLongitude: pickupLon ?? order.pickupLongitude,
          );
      await _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
    }
  }

  Future<void> _farmerMarkReady() async {
    try {
      await ref.read(deliveryRepositoryProvider).farmerMarkReady(widget.orderId);
      await _load();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
    }
  }

  Widget _buildStepper(OrderTracking t) {
    final steps = t.fulfillmentMode == 'delivery'
        ? ['searching_rider', 'rider_assigned', 'en_route_pickup', 'arrived_pickup', 'picked_up', 'in_transit', 'delivered']
        : ['pending_farmer_confirmation', 'confirmed', 'ready', 'delivered'];
    final current = t.status;
    var currentIdx = steps.indexOf(current);
    if (currentIdx < 0 && t.deliveryStatus != null) {
      currentIdx = steps.indexOf(t.deliveryStatus!);
    }

    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (var i = 0; i < steps.length; i++) ...[
            if (i > 0)
              Container(
                width: 24,
                height: 2,
                color: i <= currentIdx
                    ? Theme.of(context).colorScheme.primary
                    : Theme.of(context).colorScheme.outlineVariant,
              ),
            Column(
              children: [
                CircleAvatar(
                  radius: 12,
                  backgroundColor: i <= currentIdx
                      ? Theme.of(context).colorScheme.primary
                      : Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: Icon(
                    i < currentIdx ? Icons.check : Icons.circle,
                    size: i < currentIdx ? 14 : 8,
                    color: i <= currentIdx
                        ? Theme.of(context).colorScheme.onPrimary
                        : Theme.of(context).colorScheme.outline,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  orderStatusLabel(steps[i]),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                        fontWeight: i == currentIdx ? FontWeight.w700 : FontWeight.w400,
                      ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildLiveStrip(OrderTracking t) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.schedule, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${formatDistanceMeters(t.remainingDistanceM)} · ${formatDurationSeconds(t.remainingDurationS)}',
                    style: Theme.of(context).textTheme.titleSmall,
                  ),
                  if (t.nextStop != null)
                    Text(
                      t.nextStop == 'pickup' ? 'Heading to farm' : 'Heading to buyer',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                ],
              ),
            ),
            if (t.rider.stale && t.rider.hasCoordinates)
              Text('GPS stale', style: TextStyle(color: Theme.of(context).colorScheme.error, fontSize: 12)),
          ],
        ),
      ),
    );
  }

  Widget _buildPartyRow(String label, TrackingParty? party) {
    if (party == null || party.name.isEmpty) return const SizedBox.shrink();
    return ListTile(
      dense: true,
      contentPadding: EdgeInsets.zero,
      title: Text(label),
      subtitle: Text(party.name),
      trailing: party.phone != null
          ? IconButton(icon: const Icon(Icons.phone), onPressed: () => _callPhone(party.phone))
          : null,
    );
  }

  Widget _buildRoleActions(UserMe? user, OrderTracking t) {
    if (user?.isRider == true) {
      final ds = t.deliveryStatus ?? '';
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (['assigned', 'en_route_pickup', 'arrived_pickup', 'picked_up', 'in_transit'].contains(ds))
            OutlinedButton.icon(
              onPressed: _openExternalMaps,
              icon: const Icon(Icons.map_outlined),
              label: Text(t.nextStop == 'pickup' ? 'Open farm in Maps' : 'Open buyer in Maps'),
            ),
          const SizedBox(height: 8),
          if (ds == 'assigned')
            FilledButton(onPressed: () => _advanceRider('en_route_pickup'), child: const Text('Start to pickup')),
          if (ds == 'en_route_pickup')
            FilledButton(onPressed: () => _advanceRider('arrived_pickup'), child: const Text('Arrived at pickup')),
          if (ds == 'arrived_pickup')
            FilledButton(onPressed: () => _advanceRider('picked_up'), child: const Text('Picked up')),
          if (ds == 'picked_up')
            FilledButton(onPressed: () => _advanceRider('in_transit'), child: const Text('In transit to buyer')),
          if (ds == 'in_transit') ...[
            TextField(
              controller: _pinCtrl,
              decoration: const InputDecoration(labelText: 'Buyer PIN', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 8),
            FilledButton(onPressed: _confirmHandoffRider, child: const Text('Confirm delivery')),
          ],
        ],
      );
    }

    if (user?.isBuyer == true) {
      if (t.status == 'in_transit' || (t.status == 'picked_up' && t.fulfillmentMode == 'delivery')) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _pinCtrl,
              decoration: const InputDecoration(labelText: 'Handoff PIN', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 8),
            FilledButton(onPressed: _confirmHandoffBuyer, child: const Text('Confirm received')),
          ],
        );
      }
      if (t.status == 'ready' && t.fulfillmentMode == 'pickup') {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _pinCtrl,
              decoration: const InputDecoration(labelText: 'Handoff PIN', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 8),
            FilledButton(onPressed: _confirmHandoffBuyer, child: const Text('Confirm pickup')),
          ],
        );
      }
    }

    if (user?.isFarmer == true) {
      final order = _orderItem;
      if (order == null) return const SizedBox.shrink();
      if (order.status == 'pending_farmer_confirmation') {
        return FilledButton(
          onPressed: _farmerConfirm,
          child: Text(order.fulfillmentMode == 'delivery' ? 'Confirm & dispatch' : 'Confirm order'),
        );
      }
      if (order.status == 'confirmed' && order.fulfillmentMode == 'pickup') {
        return FilledButton(onPressed: _farmerMarkReady, child: const Text('Mark ready'));
      }
    }

    return const SizedBox.shrink();
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

    final user = ref.watch(authControllerProvider).asData?.value;
    final pickup = _toLatLng(t.pickup);
    final delivery = _toLatLng(t.delivery);
    final rider = _riderLatLng(t.rider);
    final polyline = t.routePolyline != null ? decodePolyline(t.routePolyline!) : null;
    final showMap = pickup != null || delivery != null || rider != null;
    final inProgress = !['delivered', 'cancelled', 'farmer_rejected'].contains(t.status);

    return Scaffold(
      appBar: AppBar(
        title: Text('${t.crop} order'),
        actions: [StatusChip(status: t.status)],
      ),
      body: Column(
        children: [
          if (showMap)
            Expanded(
              flex: 3,
              child: DeliveryTrackingMap(
                pickup: pickup,
                delivery: t.fulfillmentMode == 'delivery' ? delivery : null,
                rider: rider,
                polylinePoints: polyline,
                riderHeading: t.rider.heading,
                followRider: inProgress && rider != null,
              ),
            ),
          Expanded(
            flex: 2,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (t.isLiveDelivery && inProgress) _buildLiveStrip(t),
                const SizedBox(height: 12),
                _buildStepper(t),
                const SizedBox(height: 16),
                Text(
                  '${t.quantityKg.toStringAsFixed(0)} kg · ${t.fulfillmentMode}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                if (t.pricePerKg != null)
                  Text('Rs ${t.pricePerKg!.toStringAsFixed(0)}/kg · est. total Rs ${t.estimatedTotal?.toStringAsFixed(0) ?? '—'}'),
                if (t.pickup.addressLabel != null) Text('Pickup: ${t.pickup.addressLabel}'),
                if (t.delivery.addressLabel != null) Text('Delivery: ${t.delivery.addressLabel}'),
                if (t.rider.name != null) Text('Rider: ${t.rider.name}'),
                const SizedBox(height: 8),
                _buildPartyRow('Farmer', t.farmer),
                _buildPartyRow('Buyer', t.buyer),
                const Divider(height: 24),
                Text('Timeline', style: Theme.of(context).textTheme.titleSmall),
                ...t.events.map(
                  (e) => ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.history, size: 18),
                    title: Text(orderEventLabel(e.eventType)),
                    subtitle: Text('${e.createdAt}${e.detail != null ? ' · ${e.detail}' : ''}'),
                  ),
                ),
                const SizedBox(height: 16),
                _buildRoleActions(user, t),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
