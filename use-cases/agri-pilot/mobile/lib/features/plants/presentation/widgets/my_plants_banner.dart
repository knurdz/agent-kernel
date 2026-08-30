import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/widgets/section_header.dart';
import '../../../../core/widgets/start_tracking_crop_banner.dart';
import '../../../auth/domain/models.dart';

/// Horizontal "My plants" strip used on Home and Advisor.
class MyPlantsBanner extends StatelessWidget {
  const MyPlantsBanner({
    super.key,
    required this.plants,
    this.horizontalPadding = 16,
    this.compact = false,
  });

  final List<PlantSummary> plants;
  final double horizontalPadding;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (plants.isEmpty) {
      return StartTrackingCropBanner(
        margin: EdgeInsets.fromLTRB(horizontalPadding, 8, horizontalPadding, 8),
      );
    }

    if (compact) {
      return _CompactStrip(plants: plants, horizontalPadding: horizontalPadding);
    }

    return Padding(
      padding: EdgeInsets.fromLTRB(horizontalPadding, 4, horizontalPadding, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHeader(
            title: 'My plants (${plants.length})',
            actionLabel: 'See all',
            onAction: () => context.go('/home/plants'),
          ),
          SizedBox(
            height: 110,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: plants.length.clamp(0, 5),
              separatorBuilder: (_, _) => const SizedBox(width: 8),
              itemBuilder: (_, i) => _PlantCard(plant: plants[i]),
            ),
          ),
        ],
      ),
    );
  }
}

class _CompactStrip extends StatelessWidget {
  const _CompactStrip({required this.plants, required this.horizontalPadding});

  final List<PlantSummary> plants;
  final double horizontalPadding;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final visible = plants.length.clamp(0, 8);
    return Padding(
      padding: EdgeInsets.fromLTRB(horizontalPadding, 8, horizontalPadding, 4),
      child: SizedBox(
        height: 40,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: visible + 1,
          separatorBuilder: (_, _) => const SizedBox(width: 8),
          itemBuilder: (_, i) {
            if (i == 0) {
              return ActionChip(
                avatar: Icon(Icons.eco_outlined, size: 16, color: theme.colorScheme.primary),
                label: const Text('My plants'),
                onPressed: () => context.go('/home/plants'),
              );
            }
            final plant = plants[i - 1];
            return ActionChip(
              label: Text(plant.name),
              onPressed: () => context.go('/home/plants/${plant.id}'),
            );
          },
        ),
      ),
    );
  }
}

class _PlantCard extends StatelessWidget {
  const _PlantCard({required this.plant});

  final PlantSummary plant;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SizedBox(
      width: 160,
      child: Card(
        child: InkWell(
          onTap: () => context.go('/home/plants/${plant.id}'),
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(plant.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                Text(
                  '${plant.observationCount} photo${plant.observationCount == 1 ? '' : 's'}',
                  style: theme.textTheme.bodySmall,
                ),
                if (plant.latestLabel != null)
                  Text(
                    plant.latestLabel!.replaceAll('_', ' '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
