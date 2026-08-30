import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../../../config/env.dart';
import '../../../core/network/dio_client.dart';
import '../../../core/widgets/analysing_status.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/section_header.dart';
import '../../auth/domain/models.dart';
import '../data/plants_repository.dart';

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
      await ref.read(plantsRepositoryProvider).addObservation(widget.plantId, image);
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

  String _photoUrl(String? path) {
    if (path == null || path.isEmpty) return '';
    if (path.startsWith('http')) return path;
    return '${Env.apiBaseUrl}$path';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final plant = _plant;

    return Scaffold(
      appBar: AppBar(title: Text(plant?.name ?? 'Plant')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _uploading ? null : _showAttachOptions,
        icon: const Icon(Icons.add_a_photo_outlined),
        label: Text(_uploading ? 'Analyzing...' : 'Add photo'),
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
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 88),
                        children: [
                          Card(
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(plant.crop, style: theme.textTheme.titleLarge),
                                  if (plant.listingId != null)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 8),
                                      child: Chip(
                                        avatar: const Icon(Icons.link, size: 16),
                                        label: Text('Linked to listing #${plant.listingId}'),
                                      ),
                                    ),
                                  const SizedBox(height: 12),
                                  Text('Trend: ${plant.insights.trend}'),
                                  if (plant.insights.latestLabel != null)
                                    Text(
                                      'Latest: ${plant.insights.latestLabel!.replaceAll('_', ' ')}'
                                      '${plant.insights.latestConfidence != null ? ' (${(plant.insights.latestConfidence! * 100).toStringAsFixed(0)}%)' : ''}',
                                    ),
                                ],
                              ),
                            ),
                          ),
                          SectionHeader(title: 'Photo timeline (${plant.observations.length})'),
                          if (_uploading && _pendingImage != null) ...[
                            Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  ClipRRect(
                                    borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                                    child: Image.file(
                                      _pendingImage!,
                                      height: 180,
                                      width: double.infinity,
                                      fit: BoxFit.cover,
                                    ),
                                  ),
                                  const AnalysingStatus.photo(),
                                ],
                              ),
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
                              (o) => Card(
                                margin: const EdgeInsets.only(bottom: 12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    if (o.photoUrl != null)
                                      ClipRRect(
                                        borderRadius: const BorderRadius.vertical(top: Radius.circular(12)),
                                        child: Image.network(
                                          _photoUrl(o.photoUrl),
                                          height: 180,
                                          width: double.infinity,
                                          fit: BoxFit.cover,
                                          errorBuilder: (_, __, ___) => Container(
                                            height: 120,
                                            color: theme.colorScheme.surfaceContainerHighest,
                                            child: const Center(child: Icon(Icons.broken_image_outlined)),
                                          ),
                                        ),
                                      ),
                                    Padding(
                                      padding: const EdgeInsets.all(16),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(DateFormat('d MMM yyyy, HH:mm').format(o.capturedAt.toLocal())),
                                          const SizedBox(height: 4),
                                          if (!o.qualityOk)
                                            Text(o.qualityReason ?? 'Photo quality issue')
                                          else if (o.topLabel != null)
                                            Text(
                                              '${o.topLabel!.replaceAll('_', ' ')}'
                                              '${o.topConfidence != null ? ' · ${(o.topConfidence! * 100).toStringAsFixed(0)}%' : ''}',
                                            ),
                                          if (o.adviceSummary != null) ...[
                                            const SizedBox(height: 8),
                                            Text(o.adviceSummary!, style: theme.textTheme.bodySmall),
                                          ],
                                        ],
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
    );
  }
}
