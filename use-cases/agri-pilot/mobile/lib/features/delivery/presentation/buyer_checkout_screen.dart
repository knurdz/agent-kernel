import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';

import '../../../core/widgets/map_widgets.dart';
import '../../../core/widgets/status_chip.dart';
import '../../auth/domain/models.dart';
import '../data/delivery_repository.dart';

class BuyerCheckoutScreen extends ConsumerStatefulWidget {
  const BuyerCheckoutScreen({super.key, required this.listing});

  final Listing listing;

  @override
  ConsumerState<BuyerCheckoutScreen> createState() => _BuyerCheckoutScreenState();
}

class _BuyerCheckoutScreenState extends ConsumerState<BuyerCheckoutScreen> {
  final _qtyCtrl = TextEditingController();
  var _mode = 'delivery';
  var _loading = false;
  LatLng? _deliveryPin;
  String? _deliveryLabel;

  @override
  void initState() {
    super.initState();
    _qtyCtrl.text = widget.listing.displayQuantityKg.toStringAsFixed(0);
  }

  @override
  void dispose() {
    _qtyCtrl.dispose();
    super.dispose();
  }

  Future<void> _pickDelivery() async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute(
        builder: (_) => MapAddressPicker(
          initialPosition: defaultMapCenter(),
          title: 'Delivery address',
          onConfirmed: (pos, label) {
            setState(() {
              _deliveryPin = pos;
              _deliveryLabel = label;
            });
          },
        ),
      ),
    );
  }

  Future<void> _submit() async {
    final qty = double.tryParse(_qtyCtrl.text);
    if (qty == null || qty <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Enter a valid quantity')));
      return;
    }
    if (_mode == 'delivery' && _deliveryPin == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Select delivery location')));
      return;
    }
    setState(() => _loading = true);
    try {
      final repo = ref.read(deliveryRepositoryProvider);
      final result = await repo.createOrder(
        listingId: widget.listing.id,
        quantityKg: qty,
        fulfillmentMode: _mode,
        deliveryAddressLabel: _deliveryLabel,
        deliveryLatitude: _deliveryPin?.latitude,
        deliveryLongitude: _deliveryPin?.longitude,
      );
      if (!mounted) return;
      final statusMessage = result.order.status == 'searching_rider'
          ? 'We are finding a rider for your delivery.'
          : result.order.fulfillmentMode == 'pickup'
              ? 'The farmer will confirm your pickup order.'
              : orderStatusLabel(result.order.status);
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Order placed'),
          content: Text(
            '$statusMessage\n\nYour handoff PIN is ${result.handoffPin}. Share it only at pickup/delivery.\n\nPayment is cash/off-platform.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('OK'),
            ),
          ],
        ),
      );
      if (!mounted) return;
      Navigator.pop(context, true);
      context.push('/orders');
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Place order')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            '${widget.listing.crop} · max ${widget.listing.displayQuantityKg.toStringAsFixed(0)} kg',
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _qtyCtrl,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Quantity (kg)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 16),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'pickup', label: Text('Pickup'), icon: Icon(Icons.store)),
              ButtonSegment(value: 'delivery', label: Text('Delivery'), icon: Icon(Icons.local_shipping)),
            ],
            selected: {_mode},
            onSelectionChanged: (s) => setState(() => _mode = s.first),
          ),
          if (_mode == 'delivery') ...[
            const SizedBox(height: 16),
            ListTile(
              title: Text(_deliveryLabel ?? 'Tap to set delivery pin'),
              trailing: const Icon(Icons.map),
              onTap: _pickDelivery,
            ),
          ],
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _loading ? null : _submit,
            child: _loading ? const CircularProgressIndicator() : const Text('Submit order'),
          ),
        ],
      ),
    );
  }
}
