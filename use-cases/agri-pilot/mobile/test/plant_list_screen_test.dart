import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/marketplace/data/marketplace_repository.dart';
import 'package:agripilot_mobile/features/plants/data/plants_repository.dart';
import 'package:agripilot_mobile/features/plants/presentation/plant_list_screen.dart';

class _FakePlantsRepository extends PlantsRepository {
  _FakePlantsRepository() : super(Dio());

  final List<PlantSummary> _plants = [];

  @override
  Future<List<PlantSummary>> listPlants() async => List.unmodifiable(_plants);

  @override
  Future<PlantSummary> createPlant({required String crop, String? name, int? listingId}) async {
    final plant = PlantSummary(
      id: _plants.length + 1,
      crop: crop,
      name: name ?? crop,
      observationCount: 0,
      trend: 'unknown',
      createdAt: DateTime(2026, 1, 1),
      updatedAt: DateTime(2026, 1, 1),
    );
    _plants.add(plant);
    return plant;
  }
}

class _FakeMarketplaceRepository extends MarketplaceRepository {
  _FakeMarketplaceRepository() : super(Dio());

  @override
  Future<List<Listing>> farmerListings() async => [];
}

void main() {
  testWidgets('Add plant dismisses sheet and shows new crop without framework exception', (tester) async {
    final plantsRepo = _FakePlantsRepository();

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          plantsRepositoryProvider.overrideWith((ref) => plantsRepo),
          marketplaceRepositoryProvider.overrideWith((ref) => _FakeMarketplaceRepository()),
        ],
        child: const MaterialApp(home: PlantListScreen()),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('No plants yet'), findsOneWidget);

    await tester.tap(find.text('Add plant'));
    await tester.pumpAndSettle();

    expect(find.text('New plant'), findsOneWidget);

    await tester.enterText(find.byType(TextField).first, 'tomato');
    await tester.tap(find.text('Create'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(find.text('New plant'), findsNothing);
    expect(find.text('tomato'), findsWidgets);
    expect(find.text('Tracked crops (1)'), findsOneWidget);
  });
}
