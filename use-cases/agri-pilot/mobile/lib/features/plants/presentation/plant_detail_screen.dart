import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/analysing_status.dart';
import '../../../core/widgets/authenticated_photo.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/section_header.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../chat/data/chat_repository.dart';
import '../data/plants_repository.dart';
import 'widgets/plant_insights_widgets.dart';

class PlantDetailScreen extends ConsumerStatefulWidget {
  const PlantDetailScreen({super.key, required this.plantId});

  final int plantId;

  @override
  ConsumerState<PlantDetailScreen> createState() => _PlantDetailScreenState();
}

class _PlantDetailScreenState extends ConsumerState<PlantDetailScreen> {
  PlantDetail? _plant;
  var _loading = true;
  String? _error;
  var _uploading = false;
  File? _pendingImage;
  final Map<int, File> _localPhotos = {};

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
      _plant = await ref.read(plantsRepositoryProvider).getPlant(widget.plantId);
    } catch (e) {
      _error = e is ApiException ? e.message : 'Could not load plant';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: source, maxWidth: 1920, imageQuality: 85);
    if (file == null) return;
    final image = File(file.path);
    setState(() {
      _uploading = true;
      _pendingImage = image;
    });
    try {
      final obs = await ref.read(plantsRepositoryProvider).addObservation(widget.plantId, image);
      _localPhotos[obs.id] = image;
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Photo analyzed and saved')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(e))),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _uploading = false;
          _pendingImage = null;
        });
      }
    }
  }

  Future<void> _setPlantedDate() async {
    final plant = _plant;
    if (plant == null) return;
    final picked = await showDatePicker(
      context: context,
      initialDate: plant.plantedOn ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
      helpText: 'When did you plant this crop?',
    );
    if (picked == null) return;
    try {
      await ref.read(plantsRepositoryProvider).updatePlant(widget.plantId, plantedOn: picked);
      await _refresh();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(apiErrorMessage(e))),
        );
      }
    }
  }

  void _showAttachOptions() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take photo'),
              onTap: () {
                Navigator.pop(ctx);
                _pickPhoto(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose from gallery'),
              onTap: () {
                Navigator.pop(ctx);
                _pickPhoto(ImageSource.gallery);
              },
            ),
          ],
        ),
      ),
    );
  }

  void _askAdvisor() {
    final user = ref.read(authControllerProvider).value;
    final plant = _plant;
    if (user == null || plant == null) return;
    final care = plant.insights.cropCare;
    final stage = care?.currentStage?.name ?? 'unknown stage';
    final harvest = care != null && !care.needsPlantedDate
        ? 'Harvest in about ${care.daysToHarvestMinRemaining}–${care.daysToHarvestMaxRemaining} days.'
        : 'I have not set a plant date yet.';
    final diagnosis = plant.insights.latestLabel != null
        ? 'Latest scan: ${formatDiagnosisLabel(plant.insights.latestLabel)}.'
        : 'No clear diagnosis yet.';
    final summary =
        'I am tracking ${plant.crop} (${plant.name}). $diagnosis Current stage: $stage. $harvest What nutrients should I add now, and any tips for growing and harvest?';
    final sessionId = newThreadSessionId(user.id);
    context.push('/chat/t/${Uri.encodeComponent(sessionId)}', extra: summary);
  }

  PlantObservation? _latestObservation(PlantDetail plant) {
    if (plant.observations.isEmpty) return null;
    return plant.observations.last;
  }

  @override
  Widget build(BuildContext context) {
    final plant = _plant;

    return Scaffold(
      appBar: AppBar(title: Text(plant?.name ?? 'Plant')),
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (plant != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: FloatingActionButton.extended(
                heroTag: 'ask_advisor',
                onPressed: _askAdvisor,
                icon: const Icon(Icons.smart_toy_outlined),
                label: const Text('Ask advisor'),
              ),
            ),
          FloatingActionButton.extended(
            heroTag: 'add_photo',
            onPressed: _uploading ? null : _showAttachOptions,
            icon: const Icon(Icons.add_a_photo_outlined),
            label: Text(_uploading ? 'Analyzing...' : 'Add photo'),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : plant == null
                  ? const Center(child: Text('Plant not found'))
                  : RefreshIndicator(
                      onRefresh: _refresh,
                      child: ListView(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 140),
                        children: [
                          _HeroSection(
                            plant: plant,
                            latest: _latestObservation(plant),
                            localPhotos: _localPhotos,
                            pendingImage: _uploading ? _pendingImage : null,
                            onSetPlantedDate: _setPlantedDate,
                            onAddPhoto: _showAttachOptions,
                          ),
                          const SizedBox(height: 12),
                          _MetricsGrid(plant: plant),
                          const SizedBox(height: 12),
                          _WhatToDoNow(care: plant.insights.cropCare),
                          const SizedBox(height: 12),
                          if (plant.insights.cropCare != null)
                            PlantHarvestProgress(cropCare: plant.insights.cropCare!),
                          const SizedBox(height: 12),
                          PlantHealthChart(series: plant.insights.healthSeries),
                          const SizedBox(height: 12),
                          if (plant.insights.cropCare != null) ...[
                            PlantCareExpandable(
                              title: 'How to grow',
                              icon: Icons.agriculture_outlined,
                              body: plant.insights.cropCare!.howToGrow ?? '',
                            ),
                            const SizedBox(height: 8),
                            PlantCareExpandable(
                              title: 'When to harvest',
                              icon: Icons.shopping_basket_outlined,
                              body: plant.insights.cropCare!.harvestSigns ?? '',
                            ),
                            const SizedBox(height: 8),
                            PlantCareExpandable(
                              title: 'How long it takes',
                              icon: Icons.schedule_outlined,
                              body: _durationText(plant.insights.cropCare!),
                            ),
                            const SizedBox(height: 12),
                          ],
                          SectionHeader(title: 'Photo timeline (${plant.observations.length})'),
                          if (_uploading && _pendingImage != null) ...[
                            _TimelineRow(
                              capturedAt: DateTime.now(),
                              localFile: _pendingImage,
                              isUploading: true,
                            ),
                          ],
                          if (plant.observations.isEmpty && !_uploading)
                            const EmptyState(
                              icon: Icons.photo_camera_outlined,
                              title: 'No photos yet',
                              subtitle: 'Add photos over time to monitor crop health from the start.',
                            )
                          else
                            ...plant.observations.reversed.map(
                              (o) => _TimelineRow(
                                observation: o,
                                localFile: _localPhotos[o.id],
                              ),
                            ),
                        ],
                      ),
                    ),
    );
  }

  String _durationText(CropCare care) {
    final min = care.daysToHarvestMin;
    final max = care.daysToHarvestMax;
    if (min == null || max == null) return '';
    return 'Typical time from planting to harvest: $min–$max days.${care.spacing != null ? ' Spacing: ${care.spacing}' : ''}';
  }
}

class _HeroSection extends StatelessWidget {
  const _HeroSection({
    required this.plant,
    required this.latest,
    required this.localPhotos,
    required this.onSetPlantedDate,
    required this.onAddPhoto,
    this.pendingImage,
  });

  final PlantDetail plant;
  final PlantObservation? latest;
  final Map<int, File> localPhotos;
  final File? pendingImage;
  final VoidCallback onSetPlantedDate;
  final VoidCallback onAddPhoto;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final heroFile = pendingImage ?? (latest != null ? localPhotos[latest!.id] : null);
    final heroUrl = latest?.photoUrl;

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Stack(
            children: [
              if (heroFile != null || heroUrl != null)
                AuthenticatedPhoto(
                  photoUrl: heroUrl,
                  localFile: heroFile,
                  height: 200,
                  width: double.infinity,
                  fit: BoxFit.cover,
                )
              else
                InkWell(
                  onTap: onAddPhoto,
                  child: Container(
                    height: 160,
                    color: theme.colorScheme.primaryContainer.withValues(alpha: 0.35),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.add_a_photo_outlined, size: 40, color: theme.colorScheme.primary),
                        const SizedBox(height: 8),
                        const Text('Add your first photo'),
                      ],
                    ),
                  ),
                ),
              Positioned(
                top: 12,
                right: 12,
                child: PlantTrendChip(trend: plant.insights.trend),
              ),
            ],
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(plant.crop, style: theme.textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 8),
                InkWell(
                  onTap: onSetPlantedDate,
                  borderRadius: BorderRadius.circular(8),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                      children: [
                        Icon(Icons.calendar_today_outlined, size: 18, color: theme.colorScheme.primary),
                        const SizedBox(width: 8),
                        Text(
                          plant.plantedOn != null
                              ? 'Planted ${DateFormat('d MMM yyyy').format(plant.plantedOn!.toLocal())}'
                              : 'Set plant date',
                          style: theme.textTheme.bodyMedium?.copyWith(
                            color: theme.colorScheme.primary,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const Icon(Icons.chevron_right, size: 18),
                      ],
                    ),
                  ),
                ),
                if (plant.listingId != null) ...[
                  const SizedBox(height: 8),
                  Chip(
                    avatar: const Icon(Icons.link, size: 16),
                    label: Text('Linked to listing #${plant.listingId}'),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricsGrid extends StatelessWidget {
  const _MetricsGrid({required this.plant});

  final PlantDetail plant;

  @override
  Widget build(BuildContext context) {
    final care = plant.insights.cropCare;
    final daysPlanted = care?.daysSincePlanted?.toString() ?? '—';
    final stage = care?.currentStage?.name ?? '—';
    final harvestLeft = care != null && !care.needsPlantedDate
        ? '${care.daysToHarvestMinRemaining ?? '—'}'
        : '—';
    final diagnosis = formatDiagnosisLabel(plant.insights.latestLabel);

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 1.45,
      children: [
        PlantMetricTile(label: 'Days since planted', value: daysPlanted, icon: Icons.event_outlined),
        PlantMetricTile(label: 'Current stage', value: stage, icon: Icons.grass_outlined),
        PlantMetricTile(label: 'Days to harvest (min)', value: harvestLeft, icon: Icons.timer_outlined),
        PlantMetricTile(label: 'Latest diagnosis', value: diagnosis, icon: Icons.biotech_outlined),
      ],
    );
  }
}

class _WhatToDoNow extends StatelessWidget {
  const _WhatToDoNow({this.care});

  final CropCare? care;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (care == null) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Text(
            'No verified growing guide for this crop yet. Ask the advisor for general tips.',
            style: theme.textTheme.bodyMedium,
          ),
        ),
      );
    }

    final stage = care!.currentStage;
    return Card(
      color: theme.colorScheme.primaryContainer.withValues(alpha: 0.35),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.lightbulb_outline, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Text('What to do now', style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
              ],
            ),
            if (stage?.name != null) ...[
              const SizedBox(height: 8),
              Text('Stage: ${stage!.name}', style: theme.textTheme.labelLarge),
            ],
            if (stage?.nutrients != null && stage!.nutrients!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Nutrients', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
              Text(stage.nutrients!),
            ],
            if (stage?.watering != null && stage!.watering!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Watering', style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w600)),
              Text(stage.watering!),
            ],
          ],
        ),
      ),
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    this.observation,
    this.localFile,
    this.capturedAt,
    this.isUploading = false,
  });

  final PlantObservation? observation;
  final File? localFile;
  final DateTime? capturedAt;
  final bool isUploading;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final when = observation?.capturedAt ?? capturedAt ?? DateTime.now();

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AuthenticatedPhoto(
              photoUrl: observation?.photoUrl,
              localFile: localFile,
              height: 72,
              width: 72,
              fit: BoxFit.cover,
              borderRadius: BorderRadius.circular(10),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(DateFormat('d MMM yyyy, HH:mm').format(when.toLocal()),
                      style: theme.textTheme.labelMedium),
                  const SizedBox(height: 6),
                  if (isUploading)
                    const AnalysingStatus.photo(compact: true)
                  else if (observation != null && !observation!.qualityOk)
                    Text(observation!.qualityReason ?? 'Photo quality issue',
                        style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.error))
                  else if (observation?.topLabel != null)
                    Chip(
                      label: Text(
                        formatDiagnosisLabel(observation!.topLabel),
                        style: const TextStyle(fontSize: 11),
                      ),
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.zero,
                    ),
                  if (observation?.adviceSummary != null) ...[
                    const SizedBox(height: 6),
                    Text(observation!.adviceSummary!, style: theme.textTheme.bodySmall),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
