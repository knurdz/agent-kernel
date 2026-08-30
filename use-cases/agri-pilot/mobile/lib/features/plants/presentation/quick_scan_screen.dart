import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../../auth/domain/models.dart';
import '../data/plants_repository.dart';

class QuickScanScreen extends ConsumerStatefulWidget {
  const QuickScanScreen({super.key, this.initialImage, this.crop});

  final File? initialImage;
  final String? crop;

  @override
  ConsumerState<QuickScanScreen> createState() => _QuickScanScreenState();
}

class _QuickScanScreenState extends ConsumerState<QuickScanScreen> {
  ScanResult? _result;
  var _loading = false;
  String? _error;
  File? _image;

  @override
  void initState() {
    super.initState();
    _image = widget.initialImage;
    if (_image != null) _runScan();
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: source, maxWidth: 1920, imageQuality: 85);
    if (file == null) return;
    setState(() {
      _image = File(file.path);
      _result = null;
      _error = null;
    });
    await _runScan();
  }

  Future<void> _runScan() async {
    final image = _image;
    if (image == null) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await ref.read(plantsRepositoryProvider).scanPhoto(image, crop: widget.crop);
      setState(() => _result = result);
    } catch (e) {
      setState(() => _error = e is ApiException ? e.message : 'Scan failed');
    } finally {
      if (mounted) setState(() => _loading = false);
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

  Future<void> _saveToPlant() async {
    final result = _result;
    if (result == null) return;
    final crop = widget.crop ?? 'crop';
    try {
      final plant = await ref.read(plantsRepositoryProvider).createPlant(crop: crop);
      if (_image != null) {
        await ref.read(plantsRepositoryProvider).addObservation(plant.id, _image!);
      }
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Saved to your plants')));
        context.go('/home/plants/${plant.id}');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(e is ApiException ? e.message : 'Could not save plant')),
        );
      }
    }
  }

  void _askAdvisor() {
    final result = _result;
    if (result == null) return;
    final summary = result.confident && result.topLabel != null
        ? 'My crop scan shows ${result.topLabel} (${((result.topConfidence ?? 0) * 100).toStringAsFixed(0)}% confidence). What should I do?'
        : 'I scanned my crop but the diagnosis was unclear. Can you help?';
    context.go('/chat', extra: summary);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(title: const Text('Quick crop scan')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_image == null)
            EmptyState(
              icon: Icons.document_scanner_outlined,
              title: 'Scan a crop photo',
              subtitle: 'Take a photo or upload from gallery for instant disease analysis.',
              actionLabel: 'Add photo',
              onAction: _showAttachOptions,
            )
          else ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Image.file(_image!, height: 220, width: double.infinity, fit: BoxFit.cover),
            ),
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _loading ? null : _showAttachOptions,
              icon: const Icon(Icons.add_photo_alternate_outlined),
              label: const Text('Change photo'),
            ),
          ],
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
                child: Text(_error!, style: TextStyle(color: theme.colorScheme.onErrorContainer)),
              ),
            ),
          ],
          if (_result != null) ...[
            const SizedBox(height: 16),
            _ScanResultCard(result: _result!),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(onPressed: () => context.pop(), child: const Text('Done')),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: FilledButton.tonal(onPressed: _saveToPlant, child: const Text('Save to plant')),
                ),
              ],
            ),
            const SizedBox(height: 8),
            SizedBox(
              width: double.infinity,
              child: FilledButton(onPressed: _askAdvisor, child: const Text('Ask advisor')),
            ),
          ],
        ],
      ),
    );
  }
}

class _ScanResultCard extends StatelessWidget {
  const _ScanResultCard({required this.result});

  final ScanResult result;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (!result.qualityOk) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Photo quality issue', style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(result.qualityReason ?? 'Please try a clearer photo in good lighting.'),
            ],
          ),
        ),
      );
    }

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              result.confident ? 'Likely diagnosis' : 'Possible conditions',
              style: theme.textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            ...result.predictions.take(3).map(
                  (p) => Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: Row(
                      children: [
                        Expanded(child: Text(p.label.replaceAll('_', ' '))),
                        Text('${(p.confidence * 100).toStringAsFixed(0)}%'),
                      ],
                    ),
                  ),
                ),
            if (result.adviceSummary != null) ...[
              const Divider(),
              Text(result.adviceSummary!, style: theme.textTheme.bodyMedium),
            ],
          ],
        ),
      ),
    );
  }
}
