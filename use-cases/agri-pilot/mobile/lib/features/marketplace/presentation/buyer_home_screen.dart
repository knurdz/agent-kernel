import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/shell/main_shell.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/listing_card.dart';
import '../../auth/domain/models.dart';
import '../../plants/data/plants_repository.dart';
import '../data/marketplace_repository.dart';

class BuyerHomeScreen extends ConsumerStatefulWidget {
  const BuyerHomeScreen({super.key});

  @override
  ConsumerState<BuyerHomeScreen> createState() => _BuyerHomeScreenState();
}

class _BuyerHomeScreenState extends ConsumerState<BuyerHomeScreen> {
  final _crop = TextEditingController();
  final _district = TextEditingController();
  final _quantity = TextEditingController();
  List<Listing> _listings = [];
  var _loading = false;
  String? _error;
  var _searched = false;

  @override
  void dispose() {
    _crop.dispose();
    _district.dispose();
    _quantity.dispose();
    super.dispose();
  }

  Future<void> _browse() async {
    setState(() {
      _loading = true;
      _error = null;
      _searched = true;
    });
    try {
      _listings = await ref.read(marketplaceRepositoryProvider).browse(
            crop: _crop.text.trim(),
            district: _district.text.trim(),
          );
    } catch (e) {
      _listings = [];
      _error = e is ApiException ? e.message : 'Search failed. Try again.';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _match() async {
    setState(() {
      _loading = true;
      _error = null;
      _searched = true;
    });
    try {
      final qtyText = _quantity.text.trim();
      final qty = qtyText.isEmpty ? null : double.tryParse(qtyText);
      _listings = await ref.read(marketplaceRepositoryProvider).match(
            crop: _crop.text.trim(),
            district: _district.text.trim().isEmpty ? null : _district.text.trim(),
            qty: qty,
          );
    } catch (e) {
      _listings = [];
      _error = e is ApiException ? e.message : 'Match failed. Try again.';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _connect(Listing listing) async {
    try {
      await ref.read(marketplaceRepositoryProvider).connect(listing.id, message: 'Interested in your ${listing.crop}');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Connection request sent')),
        );
        ref.invalidate(pendingConnectionsCountProvider);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e is ApiException ? e.message : 'Could not connect')),
        );
      }
    }
  }

  Future<void> _showListingDetail(Listing listing) async {
    ListingInsights? insights;
    if (listing.isTracked) {
      try {
        insights = await ref.read(plantsRepositoryProvider).listingInsights(listing.id);
      } catch (_) {
        insights = null;
      }
    }

    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        final theme = Theme.of(ctx);
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  listing.crop[0].toUpperCase() + listing.crop.substring(1),
                  style: theme.textTheme.titleLarge,
                ),
                Text('${listing.quantityKg.toStringAsFixed(0)} kg'),
                if (listing.pricePerKg != null)
                  Text('Rs. ${listing.pricePerKg!.toStringAsFixed(0)}/kg'),
                if (insights != null) ...[
                  const SizedBox(height: 16),
                  Text('Crop history from the farm', style: theme.textTheme.titleMedium),
                  const SizedBox(height: 8),
                  Text('${insights.observationCount} health check${insights.observationCount == 1 ? '' : 's'} recorded'),
                  if (insights.latestLabel != null)
                    Text(
                      'Latest: ${insights.latestLabel!.replaceAll('_', ' ')}'
                      '${insights.latestConfidence != null ? ' (${(insights.latestConfidence! * 100).toStringAsFixed(0)}%)' : ''}',
                    ),
                  Text('Trend: ${insights.trend}'),
                  if (insights.timeline.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    ...insights.timeline.map(
                      (t) => Text(
                        '${t['date']}: ${(t['label'] as String?)?.replaceAll('_', ' ') ?? 'unknown'}',
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                  ],
                ] else if (listing.isTracked)
                  const Padding(
                    padding: EdgeInsets.only(top: 16),
                    child: Text('Crop is tracked but no health data is public yet.'),
                  ),
                const SizedBox(height: 16),
                FilledButton(onPressed: () {
                  Navigator.pop(ctx);
                  _connect(listing);
                }, child: const Text('Connect with farmer')),
              ],
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Marketplace'),
      ),
      body: RefreshIndicator(
        onRefresh: _browse,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(
              'Find fresh produce from local farmers',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _crop,
              decoration: const InputDecoration(
                labelText: 'Crop',
                hintText: 'e.g. tomato',
                prefixIcon: Icon(Icons.eco_outlined),
              ),
              textCapitalization: TextCapitalization.words,
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _district,
              decoration: const InputDecoration(
                labelText: 'District (optional)',
                hintText: 'e.g. Kandy',
                prefixIcon: Icon(Icons.location_on_outlined),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _quantity,
              decoration: const InputDecoration(
                labelText: 'Quantity for best match (kg, optional)',
                hintText: '100',
                prefixIcon: Icon(Icons.scale_outlined),
              ),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _loading ? null : _browse,
                    icon: const Icon(Icons.search),
                    label: const Text('Search'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _loading ? null : _match,
                    icon: const Icon(Icons.auto_awesome),
                    label: const Text('Best match'),
                  ),
                ),
              ],
            ),
            if (_loading) ...[
              const SizedBox(height: 16),
              const LinearProgressIndicator(),
            ],
            if (_error != null) ...[
              const SizedBox(height: 16),
              Card(
                color: theme.colorScheme.errorContainer,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    _error!,
                    style: TextStyle(color: theme.colorScheme.onErrorContainer),
                  ),
                ),
              ),
            ],
            const SizedBox(height: 16),
            if (!_searched && !_loading)
              const EmptyState(
                icon: Icons.search,
                title: 'Search the market',
                subtitle: 'Enter a crop name and tap Search or Best match to find listings.',
              )
            else if (_searched && !_loading && _listings.isEmpty && _error == null)
              const EmptyState(
                icon: Icons.inventory_2_outlined,
                title: 'No listings found',
                subtitle: 'Try a different crop or district.',
              )
            else
              ..._listings.map(
                (l) => ListingCard(
                  listing: l,
                  showStatus: false,
                  onTap: () => _showListingDetail(l),
                  trailing: FilledButton.tonal(
                    onPressed: () => _connect(l),
                    child: const Text('Connect'),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
