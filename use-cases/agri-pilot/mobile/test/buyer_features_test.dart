import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ListingInsights parses extended analytics fields', () {
    final insights = ListingInsights.fromJson({
      'listing_id': 1,
      'plant_id': 2,
      'crop': 'tomato',
      'observation_count': 2,
      'timeline': [],
      'health_series': [
        {'date': '2026-08-01', 'label': 'Tomato___healthy', 'confidence': 0.9, 'severity': 0},
      ],
      'trend': 'stable',
      'crop_care': {
        'current_stage': {'name': 'Vegetative'},
        'growth_progress': 0.4,
      },
      'growth_progress': 0.4,
    });

    expect(insights.healthSeries.length, 1);
    expect(insights.cropCare?.currentStage?.name, 'Vegetative');
    expect(insights.growthProgress, 0.4);
  });

  test('MatchResult parses reason and health trend', () {
    final result = MatchResult.fromJson({
      'listing': {
        'id': 1,
        'farmer_id': 2,
        'crop': 'tomato',
        'quantity_kg': 200,
        'price_per_kg': 120,
        'status': 'active',
        'plant_id': 5,
        'created_at': '2026-08-01T00:00:00Z',
        'updated_at': '2026-08-01T00:00:00Z',
      },
      'score': 250,
      'reason': 'exact district; tracked crop (stable)',
      'district': 'Kandy',
      'health': {'tracked': true, 'trend': 'stable', 'latest_label': 'Tomato___healthy'},
    });

    expect(result.reason, contains('tracked'));
    expect(result.healthTrend, 'stable');
    expect(result.listing.isTracked, isTrue);
  });

  test('UserMe exposes rider role', () {
    final rider = UserMe.fromJson({
      'id': 3,
      'phone_number': '+94770000003',
      'role': 'rider',
      'name': 'Rider',
      'subscription_status': 'none',
      'created_at': '2026-08-01T00:00:00Z',
      'profile': {'has_vehicle': true, 'is_online': false},
    });

    expect(rider.isRider, isTrue);
    expect(rider.isFarmer, isFalse);
    expect(rider.isBuyer, isFalse);
  });
}
