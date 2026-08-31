import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/location/rider_location_tracker.dart';
import '../../../core/maps/polyline_utils.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/storage/handoff_pin_store.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/section_header.dart';
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

class _OrderTrackingScreenState extends ConsumerState<OrderTrackingScreen> with SingleTickerProviderStateMixin {
  Timer? _poll;
  var _loading = true;
  OrderTracking? _tracking;
  OrderItem? _orderItem;
  final _pinCtrl = TextEditingController();
  RiderLocationTracker? _tracker;
  final _pinStore = HandoffPinStore();
  var _savedPinLoaded = false;
  var _timelineExpanded = false;
  final _mapKey = GlobalKey<DeliveryTrackingMapState>();
  late AnimationController _pulseCtrl;
  static const _mapCollapsedHeight = 112.0;

  double _mapExpandedHeight(BuildContext context) =>
      (MediaQuery.of(context).size.height * 0.34).clamp(220.0, 320.0);

  @override
  void initState() {
    super.initState();
    _pulseCtrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat(reverse: true);
    _load();
    _poll = Timer.periodic(const Duration(seconds: 5), (_) => _load(silent: true));
    _startRiderGpsIfNeeded();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _tracker?.stop();
    _pinCtrl.dispose();
    _pulseCtrl.dispose();
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

  Future<void> _copyPin() async {
    final pin = _pinCtrl.text.trim();
    if (pin.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: pin));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('PIN copied')));
    }
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

  bool _showLiveEta(OrderTracking t, bool inProgress) =>
      t.isLiveDelivery && inProgress && t.remainingDistanceM != null;

  Widget _trackingCard({required Widget child}) {
    return Card(
      child: Padding(padding: const EdgeInsets.all(16), child: child),
    );
  }

  Widget _buildHeroCard(OrderTracking t, bool inProgress) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final headline = trackingHeadline(
      status: t.status,
      deliveryStatus: t.deliveryStatus,
      fulfillmentMode: t.fulfillmentMode,
      nextStop: t.nextStop,
    );
    final icon = trackingStatusIcon(t.status, deliveryStatus: t.deliveryStatus);
    final showLive = _showLiveEta(t, inProgress);

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: scheme.primaryContainer,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Icon(icon, color: scheme.primary, size: 26),
              ),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(headline, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: 4),
                    Text(
                      orderStatusLabel(t.status),
                      style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                    ),
                  ],
                ),
              ),
              StatusChip(status: t.status),
            ],
          ),
          if (showLive) ...[
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: scheme.primary.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: scheme.primary.withValues(alpha: 0.15)),
              ),
              child: Row(
                children: [
                  _LivePulseDot(animation: _pulseCtrl, color: AppColors.primary),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '${formatDistanceMeters(t.remainingDistanceM)} · ${formatDurationSeconds(t.remainingDurationS)}',
                          style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        Text(
                          t.nextStop == 'pickup' ? 'Heading to farm' : 'Heading to buyer',
                          style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                  if (t.rider.stale && t.rider.hasCoordinates)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: scheme.errorContainer,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        'GPS stale',
                        style: theme.textTheme.labelSmall?.copyWith(color: scheme.onErrorContainer),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildProgressStepper(OrderTracking t) {
    final steps = trackingSteps(t.fulfillmentMode);
    final currentIdx = trackingStepIndex(
      status: t.status,
      deliveryStatus: t.deliveryStatus,
      fulfillmentMode: t.fulfillmentMode,
    );
    final scheme = Theme.of(context).colorScheme;

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Progress', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 14),
          Row(
            children: [
              for (var i = 0; i < steps.length; i++) ...[
                Expanded(
                  child: Column(
                    children: [
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 250),
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: i <= currentIdx ? scheme.primary : scheme.surfaceContainerHighest,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: i == currentIdx ? scheme.primary : scheme.outlineVariant,
                            width: i == currentIdx ? 2 : 1,
                          ),
                        ),
                        child: Icon(
                          i < currentIdx ? Icons.check : Icons.circle,
                          size: i < currentIdx ? 18 : 8,
                          color: i <= currentIdx ? scheme.onPrimary : scheme.outline,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        trackingStepLabel(steps[i]),
                        textAlign: TextAlign.center,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: Theme.of(context).textTheme.labelSmall?.copyWith(
                              fontWeight: i == currentIdx ? FontWeight.w700 : FontWeight.w500,
                              color: i <= currentIdx ? scheme.primary : scheme.onSurfaceVariant,
                            ),
                      ),
                    ],
                  ),
                ),
                if (i < steps.length - 1)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 18),
                    child: Container(
                      height: 2,
                      width: 8,
                      color: i < currentIdx ? scheme.primary : scheme.outlineVariant,
                    ),
                  ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildRouteCard(OrderTracking t) {
    if (t.fulfillmentMode != 'delivery') {
      if (t.pickup.addressLabel == null) return const SizedBox.shrink();
      return _trackingCard(
        child: _RouteStopRow(
          icon: Icons.storefront,
          iconColor: AppColors.primary,
          label: 'Pickup at farm',
          address: t.pickup.addressLabel!,
          active: true,
        ),
      );
    }

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Route', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          _RouteStopRow(
            icon: Icons.storefront,
            iconColor: AppColors.primary,
            label: 'From farm',
            address: t.pickup.addressLabel ?? 'Farm pickup',
            active: t.nextStop == 'pickup',
          ),
          Padding(
            padding: const EdgeInsets.only(left: 15),
            child: Container(width: 2, height: 20, color: Theme.of(context).colorScheme.outlineVariant),
          ),
          _RouteStopRow(
            icon: Icons.home,
            iconColor: AppColors.secondary,
            label: 'To buyer',
            address: t.delivery.addressLabel ?? 'Delivery address',
            active: t.nextStop == 'delivery',
          ),
        ],
      ),
    );
  }

  Widget _buildOrderSummary(OrderTracking t) {
    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  t.crop,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        color: AppColors.primaryDark,
                        fontWeight: FontWeight.w700,
                      ),
                ),
              ),
              const Spacer(),
              Text(
                t.fulfillmentMode == 'delivery' ? 'Delivery' : 'Pickup',
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          _SummaryRow(label: 'Quantity', value: '${t.quantityKg.toStringAsFixed(0)} kg'),
          if (t.pricePerKg != null) ...[
            _SummaryRow(label: 'Price', value: 'Rs ${t.pricePerKg!.toStringAsFixed(0)}/kg'),
            _SummaryRow(
              label: 'Est. total',
              value: 'Rs ${t.estimatedTotal?.toStringAsFixed(0) ?? '—'}',
              emphasized: true,
            ),
          ],
        ],
      ),
    );
  }

  Widget? _buildPinCard(UserMe? user, OrderTracking t) {
    final isBuyer = user?.isBuyer == true;
    final showSavedPin = isBuyer &&
        _pinCtrl.text.trim().length >= 4 &&
        !['delivered', 'cancelled'].contains(t.status) &&
        (t.status == 'ready' ||
            t.status == 'in_transit' ||
            t.status == 'picked_up' ||
            t.status == 'searching_rider' ||
            t.status == 'rider_assigned');

    if (!showSavedPin && !(user?.isRider == true && t.deliveryStatus == 'in_transit')) {
      return null;
    }

    if (user?.isRider == true) {
      return _trackingCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Confirm delivery', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
            const SizedBox(height: 8),
            Text(
              'Ask the buyer for their handoff PIN',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _pinCtrl,
              keyboardType: TextInputType.number,
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(letterSpacing: 8, fontWeight: FontWeight.w700),
              decoration: const InputDecoration(
                hintText: '• • • •',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
      );
    }

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Your handoff PIN',
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                ),
              ),
              TextButton.icon(
                onPressed: _copyPin,
                icon: const Icon(Icons.copy, size: 18),
                label: const Text('Copy'),
              ),
            ],
          ),
          Text(
            'Share this PIN with the rider only when you receive your produce',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 14),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              for (final ch in _pinCtrl.text.padRight(4).split('').take(4))
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Container(
                    width: 52,
                    height: 60,
                    alignment: Alignment.center,
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.primaryContainer.withValues(alpha: 0.5),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.3)),
                    ),
                    child: Text(
                      ch.trim().isEmpty ? '·' : ch,
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildContacts(OrderTracking t) {
    final parties = <({String role, TrackingParty? party, IconData icon, Color color})>[
      (role: 'Farmer', party: t.farmer, icon: Icons.agriculture, color: AppColors.primary),
      (role: 'Rider', party: t.rider.name != null ? TrackingParty(id: t.rider.id ?? 0, name: t.rider.name!, phone: t.rider.phone) : null, icon: Icons.two_wheeler, color: const Color(0xFF1565C0)),
      (role: 'Buyer', party: t.buyer, icon: Icons.person, color: AppColors.secondary),
    ];

    final visible = parties.where((p) => p.party != null && p.party!.name.isNotEmpty).toList();
    if (visible.isEmpty) return const SizedBox.shrink();

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Contacts', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          ...visible.map(
            (p) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _ContactTile(
                role: p.role,
                name: p.party!.name,
                phone: p.party!.phone,
                icon: p.icon,
                color: p.color,
                onCall: () => _callPhone(p.party!.phone),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTimeline(OrderTracking t) {
    if (t.events.isEmpty) return const SizedBox.shrink();
    final events = _timelineExpanded ? t.events : t.events.reversed.take(3).toList().reversed.toList();

    return _trackingCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SectionHeader(
            title: 'Activity',
            actionLabel: t.events.length > 3 ? (_timelineExpanded ? 'Show less' : 'Show all') : null,
            onAction: t.events.length > 3 ? () => setState(() => _timelineExpanded = !_timelineExpanded) : null,
          ),
          ...events.map(
            (e) => _TimelineRow(
              label: orderEventLabel(e.eventType),
              time: formatTrackingTimestamp(e.createdAt),
              detail: e.detail,
              isLast: e == events.last,
            ),
          ),
        ],
      ),
    );
  }

  _StickyAction? _stickyAction(UserMe? user, OrderTracking t) {
    if (user?.isRider == true) {
      final ds = t.deliveryStatus ?? '';
      if (ds == 'assigned') {
        return _StickyAction(label: 'Start to pickup', onPressed: () => _advanceRider('en_route_pickup'), icon: Icons.navigation);
      }
      if (ds == 'en_route_pickup') {
        return _StickyAction(label: 'Arrived at pickup', onPressed: () => _advanceRider('arrived_pickup'), icon: Icons.storefront);
      }
      if (ds == 'arrived_pickup') {
        return _StickyAction(label: 'Mark picked up', onPressed: () => _advanceRider('picked_up'), icon: Icons.inventory_2);
      }
      if (ds == 'picked_up') {
        return _StickyAction(label: 'In transit to buyer', onPressed: () => _advanceRider('in_transit'), icon: Icons.local_shipping);
      }
      if (ds == 'in_transit') {
        return _StickyAction(label: 'Confirm delivery', onPressed: _confirmHandoffRider, icon: Icons.check_circle);
      }
    }

    if (user?.isBuyer == true) {
      if (t.status == 'in_transit' || (t.status == 'picked_up' && t.fulfillmentMode == 'delivery')) {
        return _StickyAction(label: 'Confirm received', onPressed: _confirmHandoffBuyer, icon: Icons.check);
      }
      if (t.status == 'ready' && t.fulfillmentMode == 'pickup') {
        return _StickyAction(label: 'Confirm pickup', onPressed: _confirmHandoffBuyer, icon: Icons.check);
      }
    }

    if (user?.isFarmer == true) {
      final order = _orderItem;
      if (order == null) return null;
      if (order.status == 'pending_farmer_confirmation') {
        return _StickyAction(
          label: order.fulfillmentMode == 'delivery' ? 'Confirm & dispatch' : 'Confirm order',
          onPressed: _farmerConfirm,
          icon: Icons.check,
        );
      }
      if (order.status == 'confirmed' && order.fulfillmentMode == 'pickup') {
        return _StickyAction(label: 'Mark ready', onPressed: _farmerMarkReady, icon: Icons.done_all);
      }
    }

    return null;
  }

  @override
  Widget build(BuildContext context) {
    if (_loading && _tracking == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Track order')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final t = _tracking;
    if (t == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Track order')),
        body: const Center(child: Text('Not found')),
      );
    }

    final user = ref.watch(authControllerProvider).asData?.value;
    final pickup = _toLatLng(t.pickup);
    final delivery = _toLatLng(t.delivery);
    final rider = _riderLatLng(t.rider);
    final polyline = t.routePolyline != null ? decodePolyline(t.routePolyline!) : null;
    final showMap = pickup != null || delivery != null || rider != null;
    final inProgress = !['delivered', 'cancelled', 'farmer_rejected'].contains(t.status);
    final sticky = _stickyAction(user, t);
    final showMapsInBar = user?.isRider == true &&
        sticky != null &&
        ['assigned', 'en_route_pickup', 'arrived_pickup', 'picked_up', 'in_transit'].contains(t.deliveryStatus);
    final pinCard = _buildPinCard(user, t);
    final mapExpandedHeight = _mapExpandedHeight(context);

    return Scaffold(
      backgroundColor: AppColors.surfaceWarm,
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Order #${t.orderId}', style: Theme.of(context).textTheme.titleMedium),
            Text(
              t.crop,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
          ],
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Center(child: StatusChip(status: t.status)),
          ),
        ],
      ),
      body: CustomScrollView(
        slivers: [
          if (showMap)
            SliverPersistentHeader(
              pinned: true,
              delegate: _CollapsingMapHeaderDelegate(
                maxExtent: mapExpandedHeight,
                minExtent: _mapCollapsedHeight,
                child: DeliveryTrackingMap(
                  key: _mapKey,
                  pickup: pickup,
                  delivery: t.fulfillmentMode == 'delivery' ? delivery : null,
                  rider: rider,
                  polylinePoints: polyline,
                  riderHeading: t.rider.heading,
                  followRider: inProgress && rider != null,
                  onOpenMaps: _openExternalMaps,
                ),
              ),
            ),
          SliverPadding(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
            sliver: SliverList(
              delegate: SliverChildListDelegate([
                _buildHeroCard(t, inProgress),
                const SizedBox(height: 12),
                _buildProgressStepper(t),
                const SizedBox(height: 12),
                _buildRouteCard(t),
                const SizedBox(height: 12),
                _buildOrderSummary(t),
                if (pinCard != null) ...[
                  const SizedBox(height: 12),
                  pinCard,
                ],
                const SizedBox(height: 12),
                _buildContacts(t),
                const SizedBox(height: 12),
                _buildTimeline(t),
                SizedBox(height: sticky != null ? 88 : 16),
              ]),
            ),
          ),
        ],
      ),
      bottomNavigationBar: sticky == null
          ? null
          : SafeArea(
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.surfaceContainerLowest,
                  border: Border(top: BorderSide(color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.5))),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.06),
                      blurRadius: 12,
                      offset: const Offset(0, -4),
                    ),
                  ],
                ),
                child: showMapsInBar
                    ? Row(
                        children: [
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: _openExternalMaps,
                              icon: const Icon(Icons.map_outlined, size: 20),
                              label: Text(
                                t.nextStop == 'pickup' ? 'Open farm in Maps' : 'Open buyer in Maps',
                                overflow: TextOverflow.ellipsis,
                                maxLines: 1,
                              ),
                              style: OutlinedButton.styleFrom(
                                minimumSize: const Size.fromHeight(52),
                                padding: const EdgeInsets.symmetric(horizontal: 10),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: FilledButton.icon(
                              onPressed: sticky.onPressed,
                              icon: Icon(sticky.icon, size: 20),
                              label: Text(
                                sticky.label,
                                overflow: TextOverflow.ellipsis,
                                maxLines: 1,
                              ),
                              style: FilledButton.styleFrom(
                                minimumSize: const Size.fromHeight(52),
                                padding: const EdgeInsets.symmetric(horizontal: 10),
                              ),
                            ),
                          ),
                        ],
                      )
                    : FilledButton.icon(
                        onPressed: sticky.onPressed,
                        icon: Icon(sticky.icon),
                        label: Text(sticky.label),
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(52),
                        ),
                      ),
              ),
            ),
    );
  }
}

class _CollapsingMapHeaderDelegate extends SliverPersistentHeaderDelegate {
  _CollapsingMapHeaderDelegate({
    required this.maxExtent,
    required this.minExtent,
    required this.child,
  });

  @override
  final double maxExtent;
  @override
  final double minExtent;
  final Widget child;

  @override
  Widget build(BuildContext context, double shrinkOffset, bool overlapsContent) {
    final height = (maxExtent - shrinkOffset).clamp(minExtent, maxExtent);
    final collapsed = height <= minExtent + 4;

    return SizedBox(
      height: height,
      width: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerLowest,
          border: collapsed
              ? Border(
                  bottom: BorderSide(
                    color: Theme.of(context).colorScheme.outlineVariant.withValues(alpha: 0.5),
                  ),
                )
              : null,
          boxShadow: collapsed
              ? [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.06),
                    blurRadius: 6,
                    offset: const Offset(0, 2),
                  ),
                ]
              : null,
        ),
        child: ClipRect(
          child: Align(
            alignment: Alignment.topCenter,
            child: SizedBox(
              height: maxExtent,
              width: double.infinity,
              child: child,
            ),
          ),
        ),
      ),
    );
  }

  @override
  bool shouldRebuild(covariant _CollapsingMapHeaderDelegate oldDelegate) {
    return oldDelegate.maxExtent != maxExtent ||
        oldDelegate.minExtent != minExtent ||
        oldDelegate.child != child;
  }
}

class _StickyAction {
  _StickyAction({
    required this.label,
    required this.onPressed,
    required this.icon,
  });

  final String label;
  final VoidCallback onPressed;
  final IconData icon;
}

class _LivePulseDot extends StatelessWidget {
  const _LivePulseDot({required this.animation, required this.color});

  final Animation<double> animation;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: animation,
      builder: (context, _) {
        return Container(
          width: 12,
          height: 12,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color.withValues(alpha: 0.35 + animation.value * 0.45),
            border: Border.all(color: color, width: 2),
          ),
        );
      },
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow({required this.label, required this.value, this.emphasized = false});

  final String label;
  final String value;
  final bool emphasized;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(
        children: [
          Text(label, style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
          const Spacer(),
          Text(
            value,
            style: emphasized
                ? theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700, color: AppColors.primaryDark)
                : theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }
}

class _RouteStopRow extends StatelessWidget {
  const _RouteStopRow({
    required this.icon,
    required this.iconColor,
    required this.label,
    required this.address,
    required this.active,
  });

  final IconData icon;
  final Color iconColor;
  final String label;
  final String address;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 32,
          height: 32,
          decoration: BoxDecoration(
            color: active ? iconColor.withValues(alpha: 0.15) : scheme.surfaceContainerHighest,
            borderRadius: BorderRadius.circular(8),
            border: active ? Border.all(color: iconColor.withValues(alpha: 0.4)) : null,
          ),
          child: Icon(icon, size: 18, color: active ? iconColor : scheme.onSurfaceVariant),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600)),
              Text(
                address,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _ContactTile extends StatelessWidget {
  const _ContactTile({
    required this.role,
    required this.name,
    required this.icon,
    required this.color,
    this.phone,
    required this.onCall,
  });

  final String role;
  final String name;
  final IconData icon;
  final Color color;
  final String? phone;
  final VoidCallback onCall;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          CircleAvatar(
            radius: 20,
            backgroundColor: color.withValues(alpha: 0.15),
            child: Icon(icon, size: 20, color: color),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                Text(role, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color)),
              ],
            ),
          ),
          if (phone != null)
            IconButton.filledTonal(
              onPressed: onCall,
              icon: const Icon(Icons.phone, size: 20),
              tooltip: 'Call',
            ),
        ],
      ),
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.label,
    required this.time,
    this.detail,
    required this.isLast,
  });

  final String label;
  final String time;
  final String? detail;
  final bool isLast;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              Container(
                width: 10,
                height: 10,
                decoration: BoxDecoration(color: scheme.primary, shape: BoxShape.circle),
              ),
              if (!isLast)
                Expanded(
                  child: Container(width: 2, margin: const EdgeInsets.symmetric(vertical: 4), color: scheme.outlineVariant),
                ),
            ],
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(label, style: Theme.of(context).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                  if (time.isNotEmpty)
                    Text(time, style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
                  if (detail != null && detail!.isNotEmpty)
                    Text(detail!, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
