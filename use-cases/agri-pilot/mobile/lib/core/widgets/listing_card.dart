import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../features/auth/domain/models.dart';
import 'authenticated_photo.dart';
import 'status_chip.dart';

class ListingCard extends StatelessWidget {
  const ListingCard({
    super.key,
    required this.listing,
    this.trailing,
    this.onTap,
    this.showStatus = true,
    this.showDistrict = false,
  });

  final Listing listing;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool showStatus;
  final bool showDistrict;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final priceText = listing.pricePerKg != null
        ? 'Rs. ${listing.pricePerKg!.toStringAsFixed(0)}/kg'
        : 'Price on request';
    final dateText = DateFormat('d MMM yyyy').format(listing.createdAt.toLocal());
    final qtyText = '${listing.displayQuantityKg.toStringAsFixed(0)} kg available';

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              _ListingThumbnail(listing: listing),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Expanded(
                          child: Text(
                            _capitalize(listing.crop),
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        if (showStatus) StatusChip(status: listing.status),
                        if (listing.isTracked) ...[
                          const SizedBox(width: 6),
                          Chip(
                            label: const Text('Tracked', style: TextStyle(fontSize: 10)),
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 4),
                    Text(
                      listing.categoryLabel,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.primary,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      qtyText,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                    if (showDistrict && listing.district != null && listing.district!.isNotEmpty) ...[
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Icon(Icons.location_on_outlined, size: 14, color: theme.colorScheme.outline),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              listing.district!,
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.outline,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                    const SizedBox(height: 4),
                    Row(
                      children: [
                        Text(
                          priceText,
                          style: theme.textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w600,
                            color: theme.colorScheme.secondary,
                          ),
                        ),
                        const Spacer(),
                        Text(
                          dateText,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.outline,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              if (trailing != null) ...[
                const SizedBox(width: 8),
                trailing!,
              ],
            ],
          ),
        ),
      ),
    );
  }

  String _capitalize(String s) {
    if (s.isEmpty) return s;
    return s[0].toUpperCase() + s.substring(1);
  }
}

class _ListingThumbnail extends StatelessWidget {
  const _ListingThumbnail({required this.listing});

  final Listing listing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    if (listing.photoUrl != null && listing.photoUrl!.isNotEmpty) {
      return ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: AuthenticatedPhoto(
          photoUrl: listing.photoUrl,
          width: 56,
          height: 56,
          fit: BoxFit.cover,
        ),
      );
    }
    return Container(
      width: 56,
      height: 56,
      decoration: BoxDecoration(
        color: theme.colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(
        Icons.eco_outlined,
        color: theme.colorScheme.onPrimaryContainer,
      ),
    );
  }
}
