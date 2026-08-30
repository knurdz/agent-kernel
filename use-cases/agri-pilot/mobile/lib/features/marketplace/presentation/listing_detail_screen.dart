import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/authenticated_photo.dart';
import '../../../core/widgets/section_header.dart';
import '../../../core/widgets/status_chip.dart';
import '../../auth/domain/models.dart';
import '../../plants/data/plants_repository.dart';
import '../data/marketplace_repository.dart';

const _categories = ['vegetable', 'fruit', 'grain', 'spice', 'other'];
const _statuses = ['active', 'sold', 'expired', 'cancelled'];

class ListingDetailScreen extends ConsumerStatefulWidget {
  const ListingDetailScreen({super.key, required this.listingId});

  final int listingId;

  @override
  ConsumerState<ListingDetailScreen> createState() => _ListingDetailScreenState();
}

class _ListingDetailScreenState extends ConsumerState<ListingDetailScreen> {
  Listing? _listing;
  ListingAnalytics? _analytics;
  var _loading = true;
  var _saving = false;
  String? _error;

  late final TextEditingController _crop;
  late final TextEditingController _qty;
  late final TextEditingController _price;
  late final TextEditingController _description;
  String _category = 'vegetable';
  String _status = 'active';
  DateTime? _harvestDate;

  @override
  void initState() {
    super.initState();
    _crop = TextEditingController();
    _qty = TextEditingController();
    _price = TextEditingController();
    _description = TextEditingController();
    _load();
  }

  @override
  void dispose() {
    _crop.dispose();
    _qty.dispose();
    _price.dispose();
    _description.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(marketplaceRepositoryProvider);
      final results = await Future.wait([
        repo.listingDetail(widget.listingId),
        repo.listingAnalytics(widget.listingId),
      ]);
      final listing = results[0] as Listing;
      final analytics = results[1] as ListingAnalytics;
      _listing = listing;
      _analytics = analytics;
      _crop.text = listing.crop;
      _qty.text = listing.quantityKg.toStringAsFixed(0);
      _price.text = listing.pricePerKg?.toStringAsFixed(0) ?? '';
      _description.text = listing.description ?? '';
      _category = listing.category;
      _status = listing.status;
      _harvestDate = listing.harvestDate;
    } catch (e) {
      _error = e is ApiException ? e.message : e.toString();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _save() async {
    if (_saving) return;
    final qtyVal = double.tryParse(_qty.text.trim());
    if (_crop.text.trim().isEmpty) {
      _showSnack('Enter a crop name');
      return;
    }
    if (qtyVal == null || qtyVal <= 0) {
      _showSnack('Enter a valid quantity');
      return;
    }
    final priceText = _price.text.trim();
    final priceVal = priceText.isEmpty ? null : double.tryParse(priceText);
    if (priceText.isNotEmpty && (priceVal == null || priceVal < 0)) {
      _showSnack('Enter a valid price');
      return;
    }

    setState(() => _saving = true);
    try {
      final updated = await ref.read(marketplaceRepositoryProvider).updateListing(
            widget.listingId,
            crop: _crop.text.trim(),
            qty: qtyVal,
            price: priceVal,
            clearPrice: priceText.isEmpty,
            category: _category,
            description: _description.text.trim(),
            clearDescription: _description.text.trim().isEmpty,
            harvestDate: _harvestDate != null ? DateFormat('yyyy-MM-dd').format(_harvestDate!) : null,
            clearHarvestDate: _harvestDate == null,
            status: _status != _listing?.status ? _status : null,
          );
      _listing = updated;
      await _load();
      if (mounted) _showSnack('Listing updated');
    } catch (e) {
      _showSnack(e is ApiException ? e.message : 'Could not save listing');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: source, maxWidth: 1920, imageQuality: 85);
    if (file == null) return;
    setState(() => _saving = true);
    try {
      final updated =
          await ref.read(marketplaceRepositoryProvider).uploadListingPhoto(widget.listingId, File(file.path));
      _listing = updated;
      if (mounted) _showSnack('Photo updated');
    } catch (e) {
      _showSnack(e is ApiException ? e.message : 'Could not upload photo');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Future<void> _pickHarvestDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _harvestDate ?? DateTime.now(),
      firstDate: DateTime(2020),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked != null) setState(() => _harvestDate = picked);
  }

  Future<void> _deleteListing() async {
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
    await ref.read(marketplaceRepositoryProvider).deleteListing(widget.listingId);
    if (mounted) {
      _showSnack('Listing deleted');
      context.pop(true);
    }
  }

  Future<void> _trackListing() async {
    if (_listing == null) return;
    try {
      final plant = await ref.read(plantsRepositoryProvider).importFromListing(_listing!.id);
      await _load();
      if (mounted) {
        _showSnack('Now tracking ${_listing!.crop}');
        context.go('/home/plants/${plant.id}');
      }
    } catch (e) {
      _showSnack(e.toString());
    }
  }

  void _showSnack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final listing = _listing;
    final analytics = _analytics;

    return Scaffold(
      appBar: AppBar(
        title: Text(listing != null ? _capitalize(listing.crop) : 'Listing'),
        actions: [
          if (listing != null) StatusChip(status: listing.status),
          const SizedBox(width: 8),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text(_error!))
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
                    children: [
                      _PhotoSection(
                        listing: listing!,
                        saving: _saving,
                        onPickCamera: () => _pickPhoto(ImageSource.camera),
                        onPickGallery: () => _pickPhoto(ImageSource.gallery),
                      ),
                      const SizedBox(height: 16),
                      if (analytics != null) ...[
                        SectionHeader(title: 'Analytics'),
                        _AnalyticsGrid(analytics: analytics),
                        const SizedBox(height: 16),
                      ],
                      SectionHeader(title: 'Stock'),
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Row(
                            children: [
                              Expanded(
                                child: _StockTile(
                                  label: 'Available',
                                  value: '${(analytics?.availableKg ?? listing.displayQuantityKg).toStringAsFixed(0)} kg',
                                  color: theme.colorScheme.primary,
                                ),
                              ),
                              Expanded(
                                child: _StockTile(
                                  label: 'Reserved',
                                  value: '${(analytics?.reservedQuantityKg ?? listing.reservedQuantityKg ?? 0).toStringAsFixed(0)} kg',
                                  color: theme.colorScheme.tertiary,
                                ),
                              ),
                              Expanded(
                                child: _StockTile(
                                  label: 'Listed',
                                  value: '${listing.quantityKg.toStringAsFixed(0)} kg',
                                  color: theme.colorScheme.secondary,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      SectionHeader(title: 'Details'),
                      TextField(
                        controller: _crop,
                        decoration: const InputDecoration(labelText: 'Crop'),
                        textCapitalization: TextCapitalization.words,
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        value: _category,
                        decoration: const InputDecoration(labelText: 'Category'),
                        items: _categories
                            .map((c) => DropdownMenuItem(value: c, child: Text(_categoryLabel(c))))
                            .toList(),
                        onChanged: _saving ? null : (v) => setState(() => _category = v ?? 'vegetable'),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _description,
                        decoration: const InputDecoration(
                          labelText: 'Description (optional)',
                          hintText: 'Fresh organic produce...',
                        ),
                        maxLines: 3,
                        maxLength: 500,
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _qty,
                        decoration: const InputDecoration(labelText: 'Total quantity (kg)'),
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _price,
                        decoration: const InputDecoration(labelText: 'Price per kg (optional)'),
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                      ),
                      const SizedBox(height: 12),
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: const Text('Harvest date'),
                        subtitle: Text(
                          _harvestDate != null
                              ? DateFormat('d MMM yyyy').format(_harvestDate!)
                              : 'Not set',
                        ),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (_harvestDate != null)
                              IconButton(
                                icon: const Icon(Icons.clear),
                                onPressed: _saving ? null : () => setState(() => _harvestDate = null),
                              ),
                            IconButton(
                              icon: const Icon(Icons.calendar_today),
                              onPressed: _saving ? null : _pickHarvestDate,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      DropdownButtonFormField<String>(
                        value: _status,
                        decoration: const InputDecoration(labelText: 'Status'),
                        items: _statuses
                            .map((s) => DropdownMenuItem(value: s, child: Text(_capitalize(s))))
                            .toList(),
                        onChanged: _saving ? null : (v) => setState(() => _status = v ?? 'active'),
                      ),
                      const SizedBox(height: 16),
                      if (!listing.isTracked)
                        OutlinedButton.icon(
                          onPressed: _saving ? null : _trackListing,
                          icon: const Icon(Icons.eco_outlined),
                          label: const Text('Track this crop'),
                        )
                      else
                        OutlinedButton.icon(
                          onPressed: () => context.go('/home/plants/${listing.plantId}'),
                          icon: const Icon(Icons.link),
                          label: const Text('View tracked plant'),
                        ),
                      const SizedBox(height: 12),
                      OutlinedButton.icon(
                        onPressed: _saving ? null : _deleteListing,
                        icon: Icon(Icons.delete_outline, color: theme.colorScheme.error),
                        label: Text('Delete listing', style: TextStyle(color: theme.colorScheme.error)),
                      ),
                    ],
                  ),
                ),
      floatingActionButton: _loading || _error != null
          ? null
          : FloatingActionButton.extended(
              onPressed: _saving ? null : _save,
              icon: _saving
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                    )
                  : const Icon(Icons.save),
              label: const Text('Save changes'),
            ),
    );
  }

  String _capitalize(String s) => s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);

  String _categoryLabel(String c) {
    switch (c) {
      case 'fruit':
        return 'Fruit';
      case 'grain':
        return 'Grain';
      case 'spice':
        return 'Spice';
      case 'other':
        return 'Other';
      default:
        return 'Vegetable';
    }
  }
}

class _PhotoSection extends StatelessWidget {
  const _PhotoSection({
    required this.listing,
    required this.saving,
    required this.onPickCamera,
    required this.onPickGallery,
  });

  final Listing listing;
  final bool saving;
  final VoidCallback onPickCamera;
  final VoidCallback onPickGallery;

  @override
  Widget build(BuildContext context) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 200,
            child: listing.photoUrl != null
                ? AuthenticatedPhoto(photoUrl: listing.photoUrl, height: 200, fit: BoxFit.cover)
                : Container(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    child: Icon(Icons.image_outlined, size: 64, color: Theme.of(context).colorScheme.outline),
                  ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: saving ? null : onPickCamera,
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: const Text('Camera'),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: saving ? null : onPickGallery,
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Gallery'),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AnalyticsGrid extends StatelessWidget {
  const _AnalyticsGrid({required this.analytics});

  final ListingAnalytics analytics;

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      mainAxisSpacing: 8,
      crossAxisSpacing: 8,
      childAspectRatio: 1.6,
      children: [
        _AnalyticsTile(icon: Icons.visibility_outlined, label: 'Views', value: '${analytics.viewCount}'),
        _AnalyticsTile(
          icon: Icons.inbox_outlined,
          label: 'Requests',
          value: '${analytics.totalConnections}',
        ),
        _AnalyticsTile(icon: Icons.shopping_bag_outlined, label: 'Orders', value: '${analytics.orderCount}'),
        _AnalyticsTile(
          icon: Icons.scale_outlined,
          label: 'Kg sold',
          value: analytics.kgSold.toStringAsFixed(0),
        ),
        _AnalyticsTile(
          icon: Icons.payments_outlined,
          label: 'Revenue est.',
          value: 'Rs. ${analytics.estimatedRevenue.toStringAsFixed(0)}',
        ),
        _AnalyticsTile(
          icon: Icons.inventory_2_outlined,
          label: 'Remaining',
          value: '${analytics.availableKg.toStringAsFixed(0)} kg',
        ),
      ],
    );
  }
}

class _AnalyticsTile extends StatelessWidget {
  const _AnalyticsTile({required this.icon, required this.label, required this.value});

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, size: 20, color: theme.colorScheme.primary),
            const SizedBox(height: 4),
            Text(label, style: theme.textTheme.bodySmall),
            Text(value, style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}

class _StockTile extends StatelessWidget {
  const _StockTile({required this.label, required this.value, required this.color});

  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(value, style: TextStyle(fontWeight: FontWeight.w700, color: color, fontSize: 16)),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
