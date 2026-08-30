import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/section_header.dart';
import '../../auth/domain/models.dart';
import '../../marketplace/data/marketplace_repository.dart';
import '../data/plants_repository.dart';

class PlantListScreen extends ConsumerStatefulWidget {
  const PlantListScreen({super.key});

  @override
  ConsumerState<PlantListScreen> createState() => _PlantListScreenState();
}

class _PlantListScreenState extends ConsumerState<PlantListScreen> {
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
      _plants = await ref.read(plantsRepositoryProvider).listPlants();
    } catch (e) {
      _error = e is ApiException ? e.message : 'Could not load plants';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createPlant() async {
    final crop = TextEditingController();
    final name = TextEditingController();
    String? formError;

    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 24,
            right: 24,
            top: 8,
            bottom: MediaQuery.viewInsetsOf(ctx).bottom + 24,
          ),
          child: StatefulBuilder(
            builder: (context, setSheetState) {
              return Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text('New plant', style: Theme.of(context).textTheme.titleLarge),
                  const SizedBox(height: 16),
                  TextField(
                    controller: crop,
                    decoration: const InputDecoration(labelText: 'Crop', hintText: 'e.g. tomato'),
                    textCapitalization: TextCapitalization.words,
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: name,
                    decoration: const InputDecoration(labelText: 'Label (optional)', hintText: 'Field A tomatoes'),
                  ),
                  if (formError != null) ...[
                    const SizedBox(height: 8),
                    Text(formError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                  ],
                  const SizedBox(height: 16),
                  FilledButton(
                    onPressed: () async {
                      final cropVal = crop.text.trim();
                      if (cropVal.isEmpty) {
                        setSheetState(() => formError = 'Enter a crop name');
                        return;
                      }
                      try {
                        await ref.read(plantsRepositoryProvider).createPlant(
                              crop: cropVal,
                              name: name.text.trim().isEmpty ? null : name.text.trim(),
                            );
                        if (ctx.mounted) Navigator.pop(ctx, true);
                      } catch (e) {
                        setSheetState(() => formError = e is ApiException ? e.message : 'Could not create plant');
                      }
                    },
                    child: const Text('Create'),
                  ),
                ],
              );
            },
          ),
        );
      },
    );

    crop.dispose();
    name.dispose();
    if (created == true) await _refresh();
  }

  Future<void> _importFromListing() async {
    List<Listing> listings;
    try {
      listings = await ref.read(marketplaceRepositoryProvider).farmerListings();
      listings = listings.where((l) => !l.isTracked).toList();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e is ApiException ? e.message : 'Could not load listings')),
        );
      }
      return;
    }
    if (listings.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No unlinked listings available')),
        );
      }
      return;
    }

    if (!mounted) return;
    final selected = await showModalBottomSheet<Listing>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            const ListTile(title: Text('Import from listing')),
            ...listings.map(
              (l) => ListTile(
                title: Text(l.crop),
                subtitle: Text('${l.quantityKg.toStringAsFixed(0)} kg'),
                onTap: () => Navigator.pop(ctx, l),
              ),
            ),
          ],
        ),
      ),
    );
    if (selected == null) return;

    try {
      final plant = await ref.read(plantsRepositoryProvider).importFromListing(selected.id);
      await _refresh();
      if (mounted) context.go('/home/plants/${plant.id}');
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e is ApiException ? e.message : 'Import failed')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('My plants'),
        actions: [
          IconButton(onPressed: () => context.push('/chat/scan'), icon: const Icon(Icons.document_scanner_outlined)),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _createPlant,
        icon: const Icon(Icons.add),
        label: const Text('Add plant'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _refresh,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                children: [
                  OutlinedButton.icon(
                    onPressed: _importFromListing,
                    icon: const Icon(Icons.link),
                    label: const Text('Import from listing'),
                  ),
                  const SizedBox(height: 12),
                  if (_error != null)
                    Card(
                      color: theme.colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
                      ),
                    ),
                  SectionHeader(title: 'Tracked crops (${_plants.length})'),
                  if (_plants.isEmpty && _error == null)
                    const EmptyState(
                      icon: Icons.eco_outlined,
                      title: 'No plants yet',
                      subtitle: 'Track a crop over time with photos and AI health checks.',
                    )
                  else
                    ..._plants.map(
                      (p) => Card(
                        margin: const EdgeInsets.only(bottom: 12),
                        child: ListTile(
                          leading: CircleAvatar(
                            child: Text(p.crop.isNotEmpty ? p.crop[0].toUpperCase() : '?'),
                          ),
                          title: Text(p.name),
                          subtitle: Text(
                            '${p.observationCount} photo${p.observationCount == 1 ? '' : 's'}'
                            '${p.latestLabel != null ? ' · ${p.latestLabel!.replaceAll('_', ' ')}' : ''}',
                          ),
                          trailing: _TrendChip(trend: p.trend),
                          onTap: () => context.go('/home/plants/${p.id}'),
                        ),
                      ),
                    ),
                ],
              ),
            ),
    );
  }
}

class _TrendChip extends StatelessWidget {
  const _TrendChip({required this.trend});

  final String trend;

  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (trend) {
      'improving' => ('Improving', Colors.green),
      'worsening' => ('Worsening', Colors.orange),
      'stable' => ('Stable', Colors.blue),
      _ => ('Unknown', Colors.grey),
    };
    return Chip(
      label: Text(label, style: const TextStyle(fontSize: 11)),
      backgroundColor: color.withValues(alpha: 0.15),
      side: BorderSide.none,
      visualDensity: VisualDensity.compact,
    );
  }
}
