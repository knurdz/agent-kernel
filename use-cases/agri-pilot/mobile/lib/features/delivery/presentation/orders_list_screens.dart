import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
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
    return const ConnectionsScreen();
  }
}

class FarmerOrdersScreen extends ConsumerStatefulWidget {
  const FarmerOrdersScreen({super.key});

  @override
  ConsumerState<FarmerOrdersScreen> createState() => _FarmerOrdersScreenState();
}

class _FarmerOrdersScreenState extends ConsumerState<FarmerOrdersScreen> {
  var _loading = true;
  var _orders = <dynamic>[];

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

  Future<void> _confirm(dynamic order) async {
    LatLng? pin;
    String? label;
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => MapAddressPicker(
          initialPosition: defaultMapCenter(),
          title: 'Pickup location',
          onConfirmed: (p, l) {
            pin = p;
            label = l;
          },
        ),
      ),
    );
    await ref.read(deliveryRepositoryProvider).farmerConfirm(
          order.id as int,
          quantityKg: order.quantityKg as double,
          pickupAddressLabel: label,
          pickupLatitude: pin?.latitude,
          pickupLongitude: pin?.longitude,
        );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Orders')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.all(16),
                itemCount: _orders.length,
                itemBuilder: (_, i) {
                  final o = _orders[i];
                  return Card(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: ListTile(
                      title: Text('${o.crop} · ${o.quantityKg.toStringAsFixed(0)} kg'),
                      subtitle: Text('${o.fulfillmentMode} · ${o.status}'),
                      trailing: StatusChip(status: o.status as String),
                      onTap: () async {
                        if (o.status == 'pending_farmer_confirmation') {
                          await _confirm(o);
                        } else if (o.status == 'confirmed') {
                          await ref.read(deliveryRepositoryProvider).farmerMarkReady(o.id as int);
                          await _load();
                        }
                      },
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
  var _orders = <dynamic>[];

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
                            subtitle: Text('${o.fulfillmentMode} · ${o.status}'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => context.push('/orders/${o.id}/track'),
                          ),
                        );
                      },
                    ),
            ),
    );
  }
}
