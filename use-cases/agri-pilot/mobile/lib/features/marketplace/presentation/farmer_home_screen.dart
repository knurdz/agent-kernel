import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/domain/models.dart';
import '../data/marketplace_repository.dart';

class FarmerHomeScreen extends ConsumerStatefulWidget {
  const FarmerHomeScreen({super.key});

  @override
  ConsumerState<FarmerHomeScreen> createState() => _FarmerHomeScreenState();
}

class _FarmerHomeScreenState extends ConsumerState<FarmerHomeScreen> {
  List<Listing> _listings = [];
  var _loading = true;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    try {
      _listings = await ref.read(marketplaceRepositoryProvider).farmerListings();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createListing() async {
    final crop = TextEditingController();
    final qty = TextEditingController();
    final price = TextEditingController();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('New listing'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          TextField(controller: crop, decoration: const InputDecoration(labelText: 'Crop')),
          TextField(controller: qty, decoration: const InputDecoration(labelText: 'Quantity kg'), keyboardType: TextInputType.number),
          TextField(controller: price, decoration: const InputDecoration(labelText: 'Price/kg'), keyboardType: TextInputType.number),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Create')),
        ],
      ),
    );
    if (ok != true) return;
    await ref.read(marketplaceRepositoryProvider).createListing(
          crop: crop.text,
          qty: double.parse(qty.text),
          price: price.text.isEmpty ? null : double.parse(price.text),
        );
    await _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Farmer'),
        actions: [
          IconButton(onPressed: () => context.push('/chat'), icon: const Icon(Icons.chat)),
          IconButton(onPressed: () => context.push('/connections'), icon: const Icon(Icons.inbox)),
          IconButton(onPressed: () => context.push('/channels'), icon: const Icon(Icons.link)),
          IconButton(onPressed: () => context.push('/profile'), icon: const Icon(Icons.person)),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  FilledButton(onPressed: _createListing, child: const Text('Create listing')),
                  const SizedBox(height: 16),
                  const Text('My listings', style: TextStyle(fontWeight: FontWeight.bold)),
                  ..._listings.map(
                    (l) => ListTile(
                      title: Text('${l.crop} — ${l.quantityKg}kg'),
                      subtitle: Text('${l.status}${l.pricePerKg != null ? ' @ ${l.pricePerKg}/kg' : ''}'),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete),
                        onPressed: () async {
                          await ref.read(marketplaceRepositoryProvider).deleteListing(l.id);
                          await _refresh();
                        },
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
