import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../connections/presentation/connections_screen.dart';
import '../data/delivery_repository.dart';

class InboxScreen extends ConsumerWidget {
  const InboxScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).asData?.value;
    if (user?.isBuyer == true) {
      return const BuyerOrdersScreen();
    }
    if (user?.isFarmer == true) {
      return const FarmerOrdersScreen(showConnectionsAction: true);
    }
    return const ConnectionsScreen();
  }
}

class FarmerOrdersScreen extends ConsumerStatefulWidget {
  const FarmerOrdersScreen({super.key, this.showConnectionsAction = false});

  final bool showConnectionsAction;

  @override
  ConsumerState<FarmerOrdersScreen> createState() => _FarmerOrdersScreenState();
}

class _FarmerOrdersScreenState extends ConsumerState<FarmerOrdersScreen> {
  var _loading = true;
  var _orders = <OrderItem>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final orders = await ref.read(deliveryRepositoryProvider).farmerOrders();
      if (mounted) setState(() => _orders = orders);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _confirm(OrderItem order) async {
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
            order.id,
            quantityKg: order.quantityKg,
            pickupAddressLabel: pickupLabel ?? order.pickupAddressLabel,
            pickupLatitude: pickupLat ?? order.pickupLatitude,
            pickupLongitude: pickupLon ?? order.pickupLongitude,
          );
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    }
  }

  Future<void> _markReady(OrderItem order) async {
    try {
      await ref.read(deliveryRepositoryProvider).farmerMarkReady(order.id);
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(apiErrorMessage(e))));
      }
    }
  }

  void _openConnections() {
    Navigator.of(context).push<void>(
      MaterialPageRoute(builder: (_) => const ConnectionsScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Orders'),
        actions: [
          if (widget.showConnectionsAction)
            IconButton(
              icon: const Icon(Icons.inbox_outlined),
              tooltip: 'Buyer connections',
              onPressed: _openConnections,
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: _orders.isEmpty
                  ? ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: const [
                        SizedBox(height: 48),
                        EmptyState(
                          icon: Icons.receipt_long_outlined,
                          title: 'No orders yet',
                          subtitle: 'Orders from marketplace buys will appear here.',
                        ),
                      ],
                    )
                  : ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.all(16),
                      itemCount: _orders.length,
                      itemBuilder: (_, i) {
                        final o = _orders[i];
                        final pending = o.status == 'pending_farmer_confirmation';
                        final confirmedPickup = o.status == 'confirmed' && o.fulfillmentMode == 'pickup';
                        return Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Expanded(
                                      child: Text(
                                        '${o.crop} · ${o.quantityKg.toStringAsFixed(0)} kg',
                                        style: Theme.of(context).textTheme.titleMedium,
                                      ),
                                    ),
                                    StatusChip(status: o.status),
                                  ],
                                ),
                                const SizedBox(height: 4),
                                Text('${o.fulfillmentMode} · ${orderStatusLabel(o.status)}'),
                                if (pending || confirmedPickup) ...[
                                  const SizedBox(height: 12),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.end,
                                    children: [
                                      if (pending)
                                        FilledButton(
                                          onPressed: () => _confirm(o),
                                          child: Text(
                                            o.fulfillmentMode == 'delivery' ? 'Confirm & dispatch' : 'Confirm order',
                                          ),
                                        ),
                                      if (confirmedPickup)
                                        FilledButton(
                                          onPressed: () => _markReady(o),
                                          child: const Text('Mark ready'),
                                        ),
                                    ],
                                  ),
                                ],
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

class BuyerOrdersScreen extends ConsumerStatefulWidget {
  const BuyerOrdersScreen({super.key});

  @override
  ConsumerState<BuyerOrdersScreen> createState() => _BuyerOrdersScreenState();
}

class _BuyerOrdersScreenState extends ConsumerState<BuyerOrdersScreen> {
  var _loading = true;
  var _orders = <OrderItem>[];

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final orders = await ref.read(deliveryRepositoryProvider).buyerOrders();
      if (mounted) setState(() => _orders = orders);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('My orders')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: _orders.isEmpty
                  ? ListView(
                      physics: const AlwaysScrollableScrollPhysics(),
                      children: const [
                        SizedBox(height: 48),
                        EmptyState(
                          icon: Icons.receipt_long_outlined,
                          title: 'No orders yet',
                          subtitle: 'Your past purchases will appear here after you buy from the marketplace.',
                        ),
                      ],
                    )
                  : ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      padding: const EdgeInsets.all(16),
                      itemCount: _orders.length,
                      itemBuilder: (_, i) {
                        final o = _orders[i];
                        return Card(
                          child: ListTile(
                            title: Text('${o.crop} · ${o.quantityKg.toStringAsFixed(0)} kg'),
                            subtitle: Text('${o.fulfillmentMode} · ${orderStatusLabel(o.status)}'),
                            trailing: StatusChip(status: o.status),
                            onTap: () => context.push('/orders/${o.id}/track'),
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}
