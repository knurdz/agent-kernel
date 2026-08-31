import 'package:flutter/material.dart';

String deliveryStatusLabel(String status) {
  switch (status.toLowerCase()) {
    case 'assigned':
      return 'Assigned';
    case 'en_route_pickup':
      return 'En route to farm';
    case 'arrived_pickup':
      return 'At farm';
    case 'picked_up':
      return 'Picked up';
    case 'in_transit':
      return 'On the way to buyer';
    case 'delivered':
      return 'Delivered';
    case 'searching':
      return 'Finding rider';
    default:
      return status.replaceAll('_', ' ');
  }
}

String orderEventLabel(String eventType) {
  if (eventType.startsWith('status:')) {
    return orderStatusLabel(eventType.substring(7));
  }
  switch (eventType.toLowerCase()) {
    case 'created':
      return 'Order placed';
    case 'rider_assigned':
      return 'Rider assigned';
    default:
      return eventType.replaceAll('_', ' ');
  }
}

String formatDurationSeconds(int? seconds) {
  if (seconds == null || seconds <= 0) return '—';
  if (seconds < 60) return '< 1 min';
  final mins = (seconds / 60).round();
  if (mins < 60) return '~$mins min';
  final hrs = mins ~/ 60;
  final rem = mins % 60;
  return rem == 0 ? '~$hrs hr' : '~$hrs hr $rem min';
}

String formatDistanceMeters(int? meters) {
  if (meters == null || meters <= 0) return '—';
  if (meters < 1000) return '$meters m';
  return '${(meters / 1000).toStringAsFixed(1)} km';
}

/// Friendly headline for the tracking hero card.
String trackingHeadline({
  required String status,
  String? deliveryStatus,
  required String fulfillmentMode,
  String? nextStop,
}) {
  final effective = _effectiveTrackingStatus(status, deliveryStatus);
  switch (effective) {
    case 'pending_farmer_confirmation':
      return 'Waiting for the farm to confirm';
    case 'confirmed':
      return fulfillmentMode == 'pickup' ? 'Order confirmed — preparing pickup' : 'Order confirmed';
    case 'ready':
      return 'Your order is ready for pickup';
    case 'searching_rider':
      return 'Finding a nearby rider…';
    case 'rider_assigned':
      return 'Rider assigned — heading to farm soon';
    case 'en_route_pickup':
      return 'Rider is heading to the farm';
    case 'arrived_pickup':
      return 'Rider has arrived at the farm';
    case 'picked_up':
      return nextStop == 'delivery' ? 'Order picked up — on the way' : 'Order picked up';
    case 'in_transit':
      return 'Order is on the way to you';
    case 'delivered':
      return 'Order successfully delivered';
    case 'cancelled':
      return 'Order was cancelled';
    case 'farmer_rejected':
      return 'Order was declined by the farm';
    default:
      return orderStatusLabel(effective);
  }
}

String _effectiveTrackingStatus(String status, String? deliveryStatus) {
  const liveDelivery = {
    'assigned',
    'en_route_pickup',
    'arrived_pickup',
    'picked_up',
    'in_transit',
    'searching',
  };
  if (deliveryStatus != null && liveDelivery.contains(deliveryStatus)) {
    if (deliveryStatus == 'searching') return 'searching_rider';
    if (deliveryStatus == 'assigned') return 'rider_assigned';
    return deliveryStatus;
  }
  return status;
}

/// Compact step keys for the tracking progress bar.
List<String> trackingSteps(String fulfillmentMode) {
  if (fulfillmentMode == 'delivery') {
    return ['placed', 'rider', 'pickup', 'transit', 'delivered'];
  }
  return ['placed', 'confirmed', 'ready', 'delivered'];
}

String trackingStepLabel(String step) {
  switch (step) {
    case 'placed':
      return 'Placed';
    case 'rider':
      return 'Rider';
    case 'pickup':
      return 'Pickup';
    case 'transit':
      return 'Transit';
    case 'confirmed':
      return 'Confirmed';
    case 'ready':
      return 'Ready';
    case 'delivered':
      return 'Done';
    default:
      return step;
  }
}

int trackingStepIndex({
  required String status,
  String? deliveryStatus,
  required String fulfillmentMode,
}) {
  final effective = _effectiveTrackingStatus(status, deliveryStatus);
  if (fulfillmentMode == 'delivery') {
    const map = {
      'pending_farmer_confirmation': 0,
      'confirmed': 0,
      'ready': 0,
      'searching_rider': 1,
      'rider_assigned': 1,
      'en_route_pickup': 2,
      'arrived_pickup': 2,
      'picked_up': 3,
      'in_transit': 3,
      'delivered': 4,
    };
    return map[effective] ?? 0;
  }
  const map = {
    'pending_farmer_confirmation': 0,
    'confirmed': 1,
    'ready': 2,
    'delivered': 3,
  };
  return map[effective] ?? 0;
}

IconData trackingStatusIcon(String status, {String? deliveryStatus}) {
  final effective = _effectiveTrackingStatus(status, deliveryStatus);
  switch (effective) {
    case 'searching_rider':
      return Icons.search;
    case 'rider_assigned':
    case 'en_route_pickup':
      return Icons.two_wheeler;
    case 'arrived_pickup':
      return Icons.storefront;
    case 'picked_up':
    case 'in_transit':
      return Icons.local_shipping;
    case 'delivered':
      return Icons.check_circle;
    case 'cancelled':
    case 'farmer_rejected':
      return Icons.cancel;
    default:
      return Icons.receipt_long;
  }
}

String formatTrackingTimestamp(String? iso) {
  if (iso == null || iso.isEmpty) return '';
  try {
    final dt = DateTime.parse(iso).toLocal();
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '${dt.day}/${dt.month} $h:$m';
  } catch (_) {
    return iso;
  }
}

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
