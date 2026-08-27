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
}
