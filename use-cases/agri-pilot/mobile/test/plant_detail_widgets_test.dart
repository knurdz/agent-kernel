import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/plants/presentation/widgets/plant_insights_widgets.dart';

void main() {
  test('PlantInsights parses crop care and health series', () {
    final insights = PlantInsights.fromJson({
      'crop': 'tomato',
      'observation_count': 2,
      'trend': 'stable',
      'timeline': [],
      'health_series': [
        {'date': '2026-06-01', 'label': 'healthy', 'confidence': 0.9, 'severity': 0},
        {'date': '2026-06-08', 'label': 'early_blight', 'confidence': 0.85, 'severity': 1},
      ],
      'crop_care': {
        'crop': 'tomato',
        'how_to_grow': 'Transplant when ready.',
        'harvest_signs': 'Pick when coloured.',
        'days_to_harvest_min': 70,
        'days_to_harvest_max': 90,
        'needs_planted_date': false,
        'days_since_planted': 10,
        'days_to_harvest_min_remaining': 60,
        'days_to_harvest_max_remaining': 80,
        'growth_progress': 0.11,
        'current_stage': {'name': 'Vegetative', 'nutrients': 'Compost side-dress', 'watering': 'Deep water'},
      },
    });

    expect(insights.cropCare?.currentStage?.name, 'Vegetative');
    expect(insights.healthSeries.length, 2);
  });

  testWidgets('PlantHealthChart renders with two data points', (tester) async {
    final series = [
      HealthPoint(date: '2026-06-01', label: 'healthy', confidence: 0.9, severity: 0),
      HealthPoint(date: '2026-06-08', label: 'blight', confidence: 0.8, severity: 2),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: PlantHealthChart(series: series)),
      ),
    );

    expect(find.text('Health over time'), findsOneWidget);
  });

  testWidgets('PlantHarvestProgress shows countdown', (tester) async {
    final care = CropCare(
      daysToHarvestMinRemaining: 40,
      daysToHarvestMaxRemaining: 55,
      growthProgress: 0.4,
      harvestWindowStart: '2026-08-01',
      harvestWindowEnd: '2026-08-15',
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: PlantHarvestProgress(cropCare: care)),
      ),
    );

    expect(find.text('Days to harvest'), findsOneWidget);
    expect(find.text('40–55 days'), findsOneWidget);
  });
}
