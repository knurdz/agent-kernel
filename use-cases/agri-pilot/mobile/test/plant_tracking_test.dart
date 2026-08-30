import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/core/widgets/empty_state.dart';
import 'package:agripilot_mobile/core/widgets/listing_card.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';

void main() {
  test('Listing isTracked when plantId is set', () {
    final listing = Listing(
      id: 1,
      farmerId: 2,
      crop: 'tomato',
      quantityKg: 100,
      status: 'active',
      plantId: 5,
      createdAt: DateTime(2026, 1, 1),
    );
    expect(listing.isTracked, isTrue);
  });

  testWidgets('ListingCard shows tracked badge', (tester) async {
    final listing = Listing(
      id: 1,
      farmerId: 2,
      crop: 'tomato',
      quantityKg: 100,
      status: 'active',
      plantId: 5,
      createdAt: DateTime(2026, 1, 1),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ListingCard(listing: listing),
        ),
      ),
    );

    expect(find.text('Tracked'), findsOneWidget);
  });

  testWidgets('EmptyState Diagnose action can be wired to attach sheet callback', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: EmptyState(
            icon: Icons.smart_toy_outlined,
            title: 'Your AI farming advisor',
            actionLabel: 'Diagnose a crop',
            onAction: () {},
          ),
        ),
      ),
    );

    expect(find.text('Diagnose a crop'), findsOneWidget);
  });
}
