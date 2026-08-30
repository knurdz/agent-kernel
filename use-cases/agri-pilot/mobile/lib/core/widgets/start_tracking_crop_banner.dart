import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

class StartTrackingCropBanner extends StatelessWidget {
  const StartTrackingCropBanner({
    super.key,
    this.onTap,
    this.margin = const EdgeInsets.fromLTRB(16, 8, 16, 8),
  });

  final VoidCallback? onTap;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: margin,
      child: ListTile(
        leading: Icon(Icons.eco_outlined, color: theme.colorScheme.primary),
        title: const Text('Start tracking a crop'),
        subtitle: const Text('Monitor health from planting to harvest'),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap ?? () => context.go('/home/plants'),
      ),
    );
  }
}
