import 'package:agripilot_mobile/core/theme/app_theme.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/delivery/presentation/buyer_checkout_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Listing _listing() {
  return Listing(
    id: 1,
    farmerId: 2,
    crop: 'tomato',
    quantityKg: 100,
    pricePerKg: 80,
    status: 'active',
    createdAt: DateTime(2026, 8, 1),
    district: 'Kandy',
    farmerName: 'Amal',
    category: 'vegetable',
  );
}

void main() {
  testWidgets('Checkout defaults to delivery mode', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        home: BuyerCheckoutScreen(listing: _listing()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Delivery'), findsOneWidget);
    expect(find.text('Pickup'), findsOneWidget);
    expect(find.text('Tap to set delivery pin'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
