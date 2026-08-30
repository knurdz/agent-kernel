import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/shell/main_shell.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/listing_card.dart';
import '../../../core/widgets/section_header.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../plants/data/plants_repository.dart';
import '../../plants/presentation/widgets/my_plants_banner.dart';
import '../data/marketplace_repository.dart';

class FarmerHomeScreen extends ConsumerStatefulWidget {
  const FarmerHomeScreen({super.key});

  @override
  ConsumerState<FarmerHomeScreen> createState() => _FarmerHomeScreenState();
}

class _FarmerHomeScreenState extends ConsumerState<FarmerHomeScreen> {
  List<Listing> _listings = [];
  List<PlantSummary> _plants = [];
  var _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(marketplaceRepositoryProvider);
      final plantsRepo = ref.read(plantsRepositoryProvider);
      final results = await Future.wait([
        repo.farmerListings(),
        plantsRepo.listPlants(),
      ]);
      _listings = results[0] as List<Listing>;
      _plants = results[1] as List<PlantSummary>;
    } catch (e) {
      _error = e.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createListing() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => const _CreateListingSheet(),
    );

    if (created == true) {
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Listing created')),
        );
      }
    }
  }

  Future<void> _deleteListing(int id) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete listing?'),
        content: const Text('This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed != true) return;
    await ref.read(marketplaceRepositoryProvider).deleteListing(id);
    await _refresh();
  }

  Future<void> _trackListing(Listing listing) async {
    try {
      final plant = await ref.read(plantsRepositoryProvider).importFromListing(listing.id);
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Now tracking ${listing.crop}')),
        );
        context.go('/home/plants/${plant.id}');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e.toString())),
        );
      }
    }
  }

  void _showListingActions(Listing listing) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (!listing.isTracked)
              ListTile(
                leading: const Icon(Icons.eco_outlined),
                title: const Text('Track this crop'),
                subtitle: const Text('Monitor health and share insights with buyers'),
                onTap: () {
                  Navigator.pop(ctx);
                  _trackListing(listing);
                },
              ),
            if (listing.isTracked)
              ListTile(
                leading: const Icon(Icons.link),
                title: const Text('View tracked plant'),
                onTap: () {
                  Navigator.pop(ctx);
                  context.go('/home/plants/${listing.plantId}');
                },
              ),
            ListTile(
              leading: Icon(Icons.delete_outline, color: Theme.of(context).colorScheme.error),
              title: Text('Delete listing', style: TextStyle(color: Theme.of(context).colorScheme.error)),
              onTap: () {
                Navigator.pop(ctx);
                _deleteListing(listing.id);
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).asData?.value;
    final theme = Theme.of(context);
    final pendingAsync = ref.watch(pendingConnectionsCountProvider);
    final pendingCount = pendingAsync.asData?.value ?? 0;
    final district = user?.profile?.district;

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Hi, ${user?.name ?? 'Farmer'}'),
            if (district != null && district.isNotEmpty)
              Text(
                district,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _createListing,
        icon: const Icon(Icons.add),
        label: const Text('New listing'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                children: [
                  _AskAiCard(onTap: () => context.go('/chat')),
                  if (pendingCount > 0) ...[
                    const SizedBox(height: 12),
                    _InboxTeaser(
                      count: pendingCount,
                      onTap: () => context.go('/connections'),
                    ),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Card(
                      color: theme.colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          'Could not load data. Pull to retry.',
                          style: TextStyle(color: theme.colorScheme.onErrorContainer),
                        ),
                      ),
                    ),
                  ],
                  MyPlantsBanner(plants: _plants, horizontalPadding: 0),
                  const SizedBox(height: 16),
                  SectionHeader(title: 'My listings (${_listings.length})'),
                  if (_listings.isEmpty && _error == null)
                    const EmptyState(
                      icon: Icons.storefront_outlined,
                      title: 'No listings yet',
                      subtitle: 'Tap "New listing" to sell your harvest on the marketplace.',
                    )
                  else
                    ..._listings.map(
                      (l) => ListingCard(
                        listing: l,
                        onTap: () => _showListingActions(l),
                        trailing: IconButton(
                          icon: const Icon(Icons.more_vert),
                          onPressed: () => _showListingActions(l),
                        ),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

class _CreateListingSheet extends ConsumerStatefulWidget {
  const _CreateListingSheet();

  @override
  ConsumerState<_CreateListingSheet> createState() => _CreateListingSheetState();
}

class _CreateListingSheetState extends ConsumerState<_CreateListingSheet> {
  late final TextEditingController _crop;
  late final TextEditingController _qty;
  late final TextEditingController _price;
  String? _formError;
  var _submitting = false;

  @override
  void initState() {
    super.initState();
    _crop = TextEditingController();
    _qty = TextEditingController();
    _price = TextEditingController();
  }

  @override
  void dispose() {
    _crop.dispose();
    _qty.dispose();
    _price.dispose();
    super.dispose();
  }

  Future<void> _dismissSheet({required bool success}) async {
    FocusManager.instance.primaryFocus?.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 100));
    if (mounted) Navigator.pop(context, success);
  }

  Future<void> _submit() async {
    if (_submitting) return;
    final cropVal = _crop.text.trim();
    final qtyVal = double.tryParse(_qty.text.trim());
    if (cropVal.isEmpty) {
      setState(() => _formError = 'Enter a crop name');
      return;
    }
    if (qtyVal == null || qtyVal <= 0) {
      setState(() => _formError = 'Enter a valid quantity');
      return;
    }
    final priceVal = _price.text.trim().isEmpty ? null : double.tryParse(_price.text.trim());
    if (_price.text.trim().isNotEmpty && (priceVal == null || priceVal < 0)) {
      setState(() => _formError = 'Enter a valid price');
      return;
    }
    setState(() {
      _submitting = true;
      _formError = null;
    });
    try {
      await ref.read(marketplaceRepositoryProvider).createListing(
            crop: cropVal,
            qty: qtyVal,
            price: priceVal,
          );
      await _dismissSheet(success: true);
    } catch (e) {
      if (mounted) {
        setState(() {
          _submitting = false;
          _formError = e.toString();
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 24,
        right: 24,
        top: 8,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'New listing',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _crop,
            decoration: const InputDecoration(
              labelText: 'Crop',
              hintText: 'e.g. tomato',
            ),
            textCapitalization: TextCapitalization.words,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _qty,
            decoration: const InputDecoration(
              labelText: 'Quantity (kg)',
              hintText: '500',
            ),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _price,
            decoration: const InputDecoration(
              labelText: 'Price per kg (optional)',
              hintText: '120',
            ),
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
          ),
          if (_formError != null) ...[
            const SizedBox(height: 8),
            Text(_formError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _submitting ? null : _submit,
            child: const Text('Create listing'),
          ),
        ],
      ),
    );
  }
}

class _AskAiCard extends StatelessWidget {
  const _AskAiCard({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [
                theme.colorScheme.primary,
                theme.colorScheme.primary.withValues(alpha: 0.85),
              ],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.smart_toy, color: Colors.white, size: 28),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Ask AgriPilot',
                      style: theme.textTheme.titleMedium?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Diagnose crops, get advice, check weather',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: Colors.white.withValues(alpha: 0.9),
                      ),
                    ),
                  ],
                ),
              ),
              Icon(Icons.arrow_forward_ios, color: Colors.white.withValues(alpha: 0.8), size: 16),
            ],
          ),
        ),
      ),
    );
  }
}

class _InboxTeaser extends StatelessWidget {
  const _InboxTeaser({required this.count, required this.onTap});

  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: ListTile(
        leading: Badge(
          label: Text('$count'),
          child: Icon(Icons.inbox, color: theme.colorScheme.primary),
        ),
        title: Text('$count pending request${count == 1 ? '' : 's'}'),
        subtitle: const Text('Buyers want to connect with you'),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap,
      ),
    );
  }
}
