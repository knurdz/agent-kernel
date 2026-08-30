import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';
import '../../plants/data/plants_repository.dart';
import '../../plants/presentation/widgets/plant_insights_widgets.dart';

/// Read-only crop analytics from the farmer's tracked plant linked to a listing.
class ListingInsightsScreen extends ConsumerStatefulWidget {
  const ListingInsightsScreen({
    super.key,
    required this.listingId,
    this.listing,
  });

  final int listingId;
  final Listing? listing;

  @override
  ConsumerState<ListingInsightsScreen> createState() => _ListingInsightsScreenState();
}

class _ListingInsightsScreenState extends ConsumerState<ListingInsightsScreen> {
  ListingInsights? _insights;
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
      final insights = await ref.read(plantsRepositoryProvider).listingInsights(widget.listingId);
      if (mounted) {
        setState(() {
          _insights = insights;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _insights = null;
          _error = e is ApiException ? e.message : 'Could not load crop analytics.';
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final listing = widget.listing;
    final cropTitle = listing != null
        ? listing.crop[0].toUpperCase() + listing.crop.substring(1)
        : _insights?.crop != null
            ? _insights!.crop[0].toUpperCase() + _insights!.crop.substring(1)
            : 'Crop analytics';

    return Scaffold(
      appBar: AppBar(title: Text(cropTitle)),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                children: [
                  if (listing != null) ...[
                    Text(
                      '${listing.quantityKg.toStringAsFixed(0)} kg'
                      '${listing.pricePerKg != null ? ' · Rs. ${listing.pricePerKg!.toStringAsFixed(0)}/kg' : ''}',
                      style: Theme.of(context).textTheme.bodyLarge,
                    ),
                    const SizedBox(height: 8),
                  ],
                  Text(
                    'Crop history from this farm',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Summaries from the farmer\'s tracked crop — no photos or treatment details.',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                  ),
                  const SizedBox(height: 16),
                  if (_error != null)
                    Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Text(
                          _error!,
                          style: TextStyle(color: Theme.of(context).colorScheme.onErrorContainer),
                        ),
                      ),
                    )
                  else if (_insights == null)
                    const Card(
                      child: Padding(
                        padding: EdgeInsets.all(16),
                        child: Text('The farmer has not shared crop history for this listing yet.'),
                      ),
                    )
                  else ...[
                    Row(
                      children: [
                        PlantTrendChip(trend: _insights!.trend),
                        const SizedBox(width: 8),
                        if (_insights!.latestLabel != null)
                          Expanded(
                            child: Text(
                              'Latest: ${formatDiagnosisLabel(_insights!.latestLabel)}'
                              '${_insights!.latestConfidence != null ? ' (${(_insights!.latestConfidence! * 100).toStringAsFixed(0)}%)' : ''}',
                              style: Theme.of(context).textTheme.bodyMedium,
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Expanded(
                          child: PlantMetricTile(
                            icon: Icons.photo_camera_outlined,
                            label: 'Health checks',
                            value: '${_insights!.observationCount}',
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: PlantMetricTile(
                            icon: Icons.timeline_outlined,
                            label: 'Last check',
                            value: _insights!.lastObservationDate ?? '—',
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    if (_insights!.cropCare != null)
                      PlantHarvestProgress(cropCare: _insights!.cropCare!),
                    const SizedBox(height: 12),
                    PlantHealthChart(series: _insights!.healthSeries),
                    const SizedBox(height: 12),
                    if (_insights!.timeline.isNotEmpty) ...[
                      Text(
                        'Diagnosis timeline',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600),
                      ),
                      const SizedBox(height: 8),
                      ..._insights!.timeline.map(
                        (t) => Card(
                          child: ListTile(
                            dense: true,
                            title: Text(formatDiagnosisLabel(t['label'] as String?)),
                            subtitle: Text(t['date'] as String? ?? ''),
                            trailing: t['confidence'] != null
                                ? Text('${((t['confidence'] as num) * 100).toStringAsFixed(0)}%')
                                : null,
                          ),
                        ),
                      ),
                    ],
                    if (_insights!.cropCare != null) ...[
                      const SizedBox(height: 8),
                      PlantCareExpandable(
                        title: 'How this crop is grown',
                        icon: Icons.agriculture_outlined,
                        body: _insights!.cropCare!.howToGrow ?? '',
                      ),
                      const SizedBox(height: 8),
                      PlantCareExpandable(
                        title: 'Harvest signs',
                        icon: Icons.shopping_basket_outlined,
                        body: _insights!.cropCare!.harvestSigns ?? '',
                      ),
                    ],
                  ],
                ],
              ),
            ),
    );
  }
}
