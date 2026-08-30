import 'package:flutter/material.dart';

/// Human-readable label for marketplace order status values.
String orderStatusLabel(String status) {
  switch (status.toLowerCase()) {
    case 'pending_farmer_confirmation':
      return 'Waiting for farm';
    case 'confirmed':
      return 'Confirmed';
    case 'ready':
      return 'Ready for pickup';
    case 'searching_rider':
      return 'Finding rider';
    case 'rider_assigned':
      return 'Rider assigned';
    case 'en_route_pickup':
      return 'En route to farm';
    case 'arrived_pickup':
      return 'At farm';
    case 'picked_up':
      return 'Picked up';
    case 'in_transit':
      return 'On the way';
    case 'delivered':
      return 'Delivered';
    case 'farmer_rejected':
      return 'Rejected';
    case 'cancelled':
      return 'Cancelled';
    default:
      return status;
  }
}

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
      case 'pending_farmer_confirmation':
        return (orderStatusLabel(status), scheme.secondaryContainer, scheme.onSecondaryContainer);
      case 'accepted':
      case 'confirmed':
        return (orderStatusLabel(status), scheme.primaryContainer, scheme.onPrimaryContainer);
      case 'ready':
        return (orderStatusLabel(status), scheme.tertiaryContainer, scheme.onTertiaryContainer);
      case 'searching_rider':
      case 'rider_assigned':
      case 'en_route_pickup':
      case 'arrived_pickup':
      case 'picked_up':
      case 'in_transit':
        return (orderStatusLabel(status), scheme.primaryContainer, scheme.onPrimaryContainer);
      case 'declined':
      case 'farmer_rejected':
        return (orderStatusLabel(status), scheme.errorContainer, scheme.onErrorContainer);
      case 'completed':
      case 'delivered':
        return (orderStatusLabel(status), scheme.tertiaryContainer, scheme.onTertiaryContainer);
      case 'active':
        return ('Active', scheme.primaryContainer, scheme.onPrimaryContainer);
      case 'sold':
        return ('Sold', scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
      case 'expired':
        return ('Expired', scheme.errorContainer.withValues(alpha: 0.6), scheme.onErrorContainer);
      case 'cancelled':
        return (orderStatusLabel(status), scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
      default:
        return (orderStatusLabel(status), scheme.surfaceContainerHighest, scheme.onSurfaceVariant);
    }
  }
}
