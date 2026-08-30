import 'package:agripilot_mobile/core/theme/app_theme.dart';
import 'package:agripilot_mobile/core/widgets/listing_card.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/marketplace/data/marketplace_repository.dart';
import 'package:agripilot_mobile/features/marketplace/presentation/buyer_home_screen.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

Listing _listing({required int id, required String crop, String? district}) {
  return Listing(
    id: id,
    farmerId: 2,
    crop: crop,
    quantityKg: 100,
    pricePerKg: 80,
    status: 'active',
    createdAt: DateTime(2026, 8, 1),
    district: district,
    farmerName: 'Amal',
    category: 'vegetable',
  );
}

class _FakeMarketplaceRepository extends MarketplaceRepository {
  _FakeMarketplaceRepository(this.items) : super(Dio());

  final List<Listing> items;

  @override
  Future<List<Listing>> browse({String? crop, String? district, String? category}) async {
    return List<Listing>.from(items);
  }

  @override
  Future<List<MatchResult>> match({required String crop, String? district, double? qty}) async {
    return items
        .map((listing) => MatchResult(listing: listing, score: 10, reason: 'nearby'))
        .toList();
  }
}

Widget _buyerHome({required MarketplaceRepository repo}) {
  return ProviderScope(
    overrides: [
      marketplaceRepositoryProvider.overrideWith((ref) => repo),
    ],
    child: MaterialApp(
      theme: AppTheme.light,
      home: const BuyerHomeScreen(),
    ),
  );
}

void main() {
  testWidgets('Buyer home shows listing cards with Buy action', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final listings = [
      _listing(id: 1, crop: 'tomato', district: 'Kandy'),
      _listing(id: 2, crop: 'beans', district: 'Nuwara Eliya'),
    ];

    await tester.pumpWidget(
      _buyerHome(repo: _FakeMarketplaceRepository(listings)),
    );

    await tester.pumpAndSettle();

    expect(find.text('2 listings'), findsOneWidget);
    expect(find.byType(ListingCard), findsNWidgets(2));
    expect(find.text('Tomato'), findsOneWidget);
    expect(find.text('Beans'), findsOneWidget);
    expect(find.text('Buy'), findsNWidgets(2));
    expect(find.text('Search filters'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Listing detail shows Buy button', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final listings = [_listing(id: 1, crop: 'tomato', district: 'Kandy')];

    await tester.pumpWidget(
      _buyerHome(repo: _FakeMarketplaceRepository(listings)),
    );

    await tester.pumpAndSettle();

    await tester.tap(find.text('Tomato'));
    await tester.pumpAndSettle();

    expect(find.text('Buy'), findsAtLeastNWidgets(1));
    expect(tester.takeException(), isNull);
  });

  testWidgets('Search collapses filters after submitting', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final listings = [_listing(id: 1, crop: 'tomato', district: 'Kandy')];

    await tester.pumpWidget(
      _buyerHome(repo: _FakeMarketplaceRepository(listings)),
    );

    await tester.pumpAndSettle();

    await tester.tap(find.text('Search filters'));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsNWidgets(3));

    await tester.tap(find.text('Search'));
    await tester.pumpAndSettle();

    expect(find.byType(TextField), findsNothing);
    expect(find.text('1 listing'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('ListingCard with Buy trailing keeps crop title visible', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: Scaffold(
          body: ListingCard(
            listing: _listing(id: 1, crop: 'tomato', district: 'Kandy'),
            showStatus: false,
            showDistrict: true,
            trailing: FilledButton(onPressed: () {}, child: const Text('Buy')),
          ),
        ),
      ),
    );

    expect(find.text('Tomato'), findsOneWidget);
    expect(find.text('Kandy'), findsOneWidget);
    expect(find.text('Buy'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
