import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../marketplace/data/marketplace_repository.dart';

class ConnectionsScreen extends ConsumerStatefulWidget {
  const ConnectionsScreen({super.key});

  @override
  ConsumerState<ConnectionsScreen> createState() => _ConnectionsScreenState();
}

class _ConnectionsScreenState extends ConsumerState<ConnectionsScreen> {
  List<ConnectionItem> _items = [];
  var _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final user = ref.read(authControllerProvider).asData?.value;
      final repo = ref.read(marketplaceRepositoryProvider);
      _items = user?.isFarmer == true ? await repo.farmerConnections() : await repo.buyerConnections();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _showContact(ConnectionItem item) async {
    final user = ref.read(authControllerProvider).asData?.value;
    final repo = ref.read(marketplaceRepositoryProvider);
    try {
      final phone = user?.isFarmer == true
          ? await repo.farmerContact(item.id)
          : await repo.buyerContact(item.id);
      final uri = Uri.parse('tel:$phone');
      if (await canLaunchUrl(uri)) await launchUrl(uri);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.toString())));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final isFarmer = ref.watch(authControllerProvider).asData?.value?.isFarmer == true;
    return Scaffold(
      appBar: AppBar(title: const Text('Connections'), leading: BackButton(onPressed: () => context.pop())),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView.builder(
                itemCount: _items.length,
                itemBuilder: (_, i) {
                  final c = _items[i];
                  return ListTile(
                    title: Text('${c.listing.crop} — ${c.status}'),
                    subtitle: Text(c.message ?? ''),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (isFarmer && c.status == 'pending')
                          IconButton(
                            icon: const Icon(Icons.check),
                            onPressed: () async {
                              await ref.read(marketplaceRepositoryProvider).patchConnection(c.id, 'accepted');
                              await _load();
                            },
                          ),
                        if (c.status == 'accepted' || c.status == 'completed')
                          IconButton(icon: const Icon(Icons.phone), onPressed: () => _showContact(c)),
                      ],
                    ),
                  );
                },
              ),
            ),
    );
  }
}
