import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/shell/main_shell.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/status_chip.dart';
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
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final user = ref.read(authControllerProvider).asData?.value;
      final repo = ref.read(marketplaceRepositoryProvider);
      _items = user?.isFarmer == true ? await repo.farmerConnections() : await repo.buyerConnections();
      ref.invalidate(pendingConnectionsCountProvider);
    } catch (e) {
      _error = e.toString();
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

  Future<void> _patchConnection(ConnectionItem item, String status) async {
    await ref.read(marketplaceRepositoryProvider).patchConnection(item.id, status);
    await _load();
  }

  String _capitalize(String s) {
    if (s.isEmpty) return s;
    return s[0].toUpperCase() + s.substring(1);
  }

  @override
  Widget build(BuildContext context) {
    final isFarmer = ref.watch(authControllerProvider).asData?.value?.isFarmer == true;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Inbox'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: _error != null
                  ? ListView(
                      children: [
                        Card(
                          margin: const EdgeInsets.all(16),
                          color: theme.colorScheme.errorContainer,
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              'Could not load connections. Pull to retry.',
                              style: TextStyle(color: theme.colorScheme.onErrorContainer),
                            ),
                          ),
                        ),
                      ],
                    )
                  : _items.isEmpty
                      ? ListView(
                          children: const [
                            EmptyState(
                              icon: Icons.handshake_outlined,
                              title: 'No deals yet',
                              subtitle: 'When buyers connect with your listings, or you reach out to farmers, they will appear here.',
                            ),
                          ],
                        )
                      : ListView.builder(
                          padding: const EdgeInsets.all(16),
                          itemCount: _items.length,
                          itemBuilder: (_, i) {
                            final c = _items[i];
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
                                            _capitalize(c.listing.crop),
                                            style: theme.textTheme.titleMedium?.copyWith(
                                              fontWeight: FontWeight.w600,
                                            ),
                                          ),
                                        ),
                                        StatusChip(status: c.status),
                                      ],
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '${c.listing.quantityKg.toStringAsFixed(0)} kg'
                                      '${c.listing.pricePerKg != null ? ' · Rs. ${c.listing.pricePerKg!.toStringAsFixed(0)}/kg' : ''}',
                                      style: theme.textTheme.bodyMedium?.copyWith(
                                        color: theme.colorScheme.onSurfaceVariant,
                                      ),
                                    ),
                                    if (c.message != null && c.message!.isNotEmpty) ...[
                                      const SizedBox(height: 8),
                                      Text(
                                        '"${c.message!}"',
                                        style: theme.textTheme.bodySmall?.copyWith(
                                          fontStyle: FontStyle.italic,
                                          color: theme.colorScheme.onSurfaceVariant,
                                        ),
                                      ),
                                    ],
                                    const SizedBox(height: 12),
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.end,
                                      children: [
                                        if (isFarmer && c.status == 'pending') ...[
                                          TextButton(
                                            onPressed: () => _patchConnection(c, 'declined'),
                                            child: const Text('Decline'),
                                          ),
                                          const SizedBox(width: 8),
                                          FilledButton(
                                            onPressed: () => _patchConnection(c, 'accepted'),
                                            child: const Text('Accept'),
                                          ),
                                        ] else if (c.status == 'accepted' || c.status == 'completed')
                                          FilledButton.tonalIcon(
                                            onPressed: () => _showContact(c),
                                            icon: const Icon(Icons.phone, size: 18),
                                            label: const Text('Call'),
                                          ),
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
