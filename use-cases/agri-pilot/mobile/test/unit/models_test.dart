import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/features/auth/domain/models.dart';

void main() {
  test('UserMe parses farmer JSON', () {
    final user = UserMe.fromJson({
      'id': 1,
      'phone_number': '+94770000001',
      'role': 'farmer',
      'subscription_status': 'active',
      'name': 'Amal',
      'created_at': '2026-01-01T00:00:00Z',
      'profile': {'district': 'Kandy'},
    });
    expect(user.isFarmer, isTrue);
    expect(user.isActiveFarmer, isTrue);
  });

  test('Listing parses crop listing', () {
    final listing = Listing.fromJson({
      'id': 2,
      'farmer_id': 1,
      'crop': 'tomato',
      'quantity_kg': 500,
      'price_per_kg': 120,
      'status': 'active',
      'created_at': '2026-01-01T00:00:00Z',
    });
    expect(listing.crop, 'tomato');
  test('UserMe parses rider JSON', () {
    final user = UserMe.fromJson({
      'id': 3,
      'phone_number': '+94770000003',
      'role': 'rider',
      'subscription_status': 'none',
      'name': 'Ravi',
      'created_at': '2026-01-01T00:00:00Z',
      'profile': {'has_vehicle': true, 'is_online': false},
    });
    expect(user.isRider, isTrue);
  });

  test('OrderItem parses delivery order', () {
    final order = OrderItem.fromJson({
      'id': 1,
      'connection_id': 2,
      'listing_id': 3,
      'crop': 'tomato',
      'quantity_kg': 50,
      'fulfillment_mode': 'delivery',
      'status': 'searching_rider',
      'created_at': '2026-01-01T00:00:00Z',
      'updated_at': '2026-01-01T00:00:00Z',
    });
    expect(order.fulfillmentMode, 'delivery');
    expect(order.status, 'searching_rider');
  });
}
