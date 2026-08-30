import 'package:flutter/material.dart';

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    final (label, bg, fg) = _style(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: fg,
              fontWeight: FontWeight.w600,
            ),
      ),
    );
  }

  (String, Color, Color) _style(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    switch (status.toLowerCase()) {
      case 'pending':
        return ('Pending', scheme.secondaryContainer, scheme.onSecondaryContainer);
      case 'accepted':
        return ('Accepted', scheme.primaryContainer, scheme.onPrimaryContainer);
      case 'declined':
        return ('Declined', scheme.errorContainer, scheme.onErrorContainer);
      case 'completed':
        return ('Completed', scheme.tertiaryContainer, scheme.onTertiaryContainer);
      case 'active':
        return ('Active', scheme.primaryContainer, scheme.onPrimaryContainer);
      case 'sold':
        return ('Sold', scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
      case 'expired':
        return ('Expired', scheme.errorContainer.withValues(alpha: 0.6), scheme.onErrorContainer);
      case 'cancelled':
        return ('Cancelled', scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
      default:
        return (status, scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
    }
  }
}
