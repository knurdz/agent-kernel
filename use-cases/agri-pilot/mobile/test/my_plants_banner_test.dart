import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/plants/presentation/widgets/my_plants_banner.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

PlantSummary _plant({required String name, String crop = 'tomato'}) {
  return PlantSummary(
    id: 1,
    crop: crop,
    name: name,
    observationCount: 2,
    latestLabel: 'early_blight',
    trend: 'stable',
    createdAt: DateTime(2026, 1, 1),
    updatedAt: DateTime(2026, 1, 1),
  );
}

void main() {
  testWidgets('empty banner prompts the farmer to start tracking', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: MyPlantsBanner(plants: [])),
      ),
    );

    expect(find.text('Start tracking a crop'), findsOneWidget);
  });

  testWidgets('banner lists tracked plants', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MyPlantsBanner(plants: [_plant(name: 'Field tomatoes')]),
        ),
      ),
    );

    expect(find.text('My plants (1)'), findsOneWidget);
    expect(find.text('Field tomatoes'), findsOneWidget);
    expect(find.text('2 photos'), findsOneWidget);
  });

  testWidgets('compact banner shows a my plants chip', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: MyPlantsBanner(
            plants: [_plant(name: 'Field tomatoes')],
            compact: true,
          ),
        ),
      ),
    );

    expect(find.text('My plants'), findsOneWidget);
    expect(find.text('Field tomatoes'), findsOneWidget);
  });
}
