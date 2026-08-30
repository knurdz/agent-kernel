import 'package:agripilot_mobile/core/theme/app_theme.dart';
import 'package:agripilot_mobile/core/widgets/status_chip.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/delivery/data/delivery_repository.dart';
import 'package:agripilot_mobile/features/delivery/presentation/orders_list_screens.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

class _FakeDeliveryRepository extends DeliveryRepository {
  _FakeDeliveryRepository(this.orders) : super(Dio());

  final List<OrderItem> orders;

  @override
  Future<List<OrderItem>> farmerOrders() async => orders;
}

void main() {
  testWidgets('Farmer inbox orders screen shows confirm button for pending pickup', (tester) async {
    final orders = [
      OrderItem(
        id: 1,
        connectionId: 1,
        listingId: 1,
        crop: 'tomato',
        quantityKg: 50,
        fulfillmentMode: 'pickup',
        status: 'pending_farmer_confirmation',
      ),
    ];

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          deliveryRepositoryProvider.overrideWith((ref) => _FakeDeliveryRepository(orders)),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const FarmerOrdersScreen(),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Confirm order'), findsOneWidget);
    expect(find.text('Waiting for farm'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
