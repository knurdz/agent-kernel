import 'package:agripilot_mobile/core/maps/polyline_utils.dart';
import 'package:agripilot_mobile/core/widgets/status_chip.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';

void main() {
  test('decodePolyline decodes a simple encoded string', () {
    // Encoded polyline for roughly Kandy area (sample points)
    const encoded = '_p~iF~ps|U_ulLnnqC_mqNvxq`@';
    final points = decodePolyline(encoded);
    expect(points, isNotEmpty);
    expect(points.first, isA<LatLng>());
  });

  test('OrderTracking.fromJson parses enriched tracking payload', () {
    final tracking = OrderTracking.fromJson({
      'order_id': 42,
      'delivery_id': 7,
      'status': 'in_transit',
      'fulfillment_mode': 'delivery',
      'quantity_kg': 50,
      'crop': 'tomato',
      'price_per_kg': 120,
      'estimated_total': 6000,
      'created_at': '2026-08-01T00:00:00Z',
      'assigned_at': '2026-08-01T01:00:00Z',
      'pickup': {'address_label': 'Farm', 'latitude': 7.29, 'longitude': 80.63},
      'delivery': {'address_label': 'Shop', 'latitude': 7.30, 'longitude': 80.64},
      'farmer': {'id': 1, 'name': 'Farmer', 'phone': '+94770000001'},
      'buyer': {'id': 2, 'name': 'Buyer'},
      'rider': {
        'id': 3,
        'name': 'Rider',
        'latitude': 7.285,
        'longitude': 80.635,
        'heading': 90,
        'stale': false,
      },
      'delivery_status': 'in_transit',
      'next_stop': 'delivery',
      'remaining_distance_m': 1500,
      'remaining_duration_s': 300,
      'route_polyline': '_p~iF~ps|U',
      'route_distance_m': 2000,
      'route_duration_s': 400,
      'maps_available': true,
      'events': [
        {'event_type': 'status:picked_up', 'created_at': '2026-08-01T02:00:00Z'},
      ],
    });

    expect(tracking.orderId, 42);
    expect(tracking.deliveryId, 7);
    expect(tracking.nextStop, 'delivery');
    expect(tracking.remainingDistanceM, 1500);
    expect(tracking.rider.name, 'Rider');
    expect(tracking.farmer?.name, 'Farmer');
    expect(tracking.isLiveDelivery, isTrue);
    expect(tracking.events.first.eventType, 'status:picked_up');
  });

  test('orderEventLabel humanizes status events', () {
    expect(orderEventLabel('status:picked_up'), 'Picked up');
    expect(orderEventLabel('rider_assigned'), 'Rider assigned');
    expect(orderEventLabel('created'), 'Order placed');
  });

  test('deliveryStatusLabel maps delivery statuses', () {
    expect(deliveryStatusLabel('in_transit'), 'On the way to buyer');
    expect(deliveryStatusLabel('assigned'), 'Assigned');
  });

  test('formatDistanceMeters and formatDurationSeconds', () {
    expect(formatDistanceMeters(850), '850 m');
    expect(formatDistanceMeters(2400), '2.4 km');
    expect(formatDurationSeconds(180), '~3 min');
  });

  test('OrderItem parses delivery coordinates', () {
    final item = OrderItem.fromJson({
      'id': 1,
      'connection_id': 2,
      'listing_id': 3,
      'crop': 'tomato',
      'quantity_kg': 10,
      'fulfillment_mode': 'delivery',
      'status': 'searching_rider',
      'delivery_latitude': 7.30,
      'delivery_longitude': 80.64,
    });
    expect(item.deliveryLatitude, 7.30);
    expect(item.deliveryLongitude, 80.64);
  });
}
