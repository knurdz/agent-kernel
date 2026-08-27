import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/domain/models.dart';
import '../data/marketplace_repository.dart';

class BuyerHomeScreen extends ConsumerStatefulWidget {
  const BuyerHomeScreen({super.key});

  @override
  ConsumerState<BuyerHomeScreen> createState() => _BuyerHomeScreenState();
}

class _BuyerHomeScreenState extends ConsumerState<BuyerHomeScreen> {
  final _crop = TextEditingController(text: 'tomato');
  final _district = TextEditingController(text: 'Kandy');
  List<Listing> _listings = [];
  var _loading = false;

  Future<void> _browse() async {
    setState(() => _loading = true);
    try {
      _listings = await ref.read(marketplaceRepositoryProvider).browse(
            crop: _crop.text,
            district: _district.text,
          );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _match() async {
    setState(() => _loading = true);
    try {
      _listings = await ref.read(marketplaceRepositoryProvider).match(
            crop: _crop.text,
            district: _district.text,
            qty: 100,
          );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Buyer'),
        actions: [
          IconButton(onPressed: () => context.push('/chat'), icon: const Icon(Icons.chat)),
          IconButton(onPressed: () => context.push('/connections'), icon: const Icon(Icons.handshake)),
          IconButton(onPressed: () => context.push('/profile'), icon: const Icon(Icons.person)),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(controller: _crop, decoration: const InputDecoration(labelText: 'Crop')),
          TextField(controller: _district, decoration: const InputDecoration(labelText: 'District')),
          Row(
            children: [
              FilledButton(onPressed: _loading ? null : _browse, child: const Text('Browse')),
              const SizedBox(width: 8),
              OutlinedButton(onPressed: _loading ? null : _match, child: const Text('Match')),
            ],
          ),
          if (_loading) const LinearProgressIndicator(),
          ..._listings.map(
            (l) => Card(
              child: ListTile(
                title: Text('${l.crop} — ${l.quantityKg}kg'),
                subtitle: Text(l.pricePerKg != null ? '${l.pricePerKg}/kg' : 'Price on request'),
                trailing: IconButton(
                  icon: const Icon(Icons.connect_without_contact),
                  onPressed: () async {
                    await ref.read(marketplaceRepositoryProvider).connect(l.id, message: 'Interested');
                    if (context.mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Connection requested')));
                    }
                  },
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
