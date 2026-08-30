import 'package:agripilot_mobile/core/notifications/push_service.dart';
import 'package:agripilot_mobile/core/shell/main_shell.dart';
import 'package:agripilot_mobile/core/storage/secure_token_store.dart';
import 'package:agripilot_mobile/core/theme/app_theme.dart';
import 'package:agripilot_mobile/features/auth/data/auth_repository.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/auth/providers/auth_provider.dart';
import 'package:agripilot_mobile/features/connections/presentation/connections_screen.dart';
import 'package:agripilot_mobile/features/marketplace/data/marketplace_repository.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

Listing _listing({required int id, required String crop}) {
  return Listing(
    id: id,
    farmerId: 1,
    crop: crop,
    quantityKg: 200,
    pricePerKg: 120,
    status: 'active',
    createdAt: DateTime(2026, 8, 1),
    category: 'vegetable',
  );
}

ConnectionItem _pendingConnection() {
  return ConnectionItem(
    id: 1,
    listingId: 10,
    status: 'pending',
    message: 'Need 200kg',
    listing: _listing(id: 10, crop: 'tomato'),
    buyer: BuyerPublic(id: 5, name: 'Buyer One', district: 'Colombo', businessName: 'Fresh Mart'),
  );
}

class _FakeSecureTokenStore extends SecureTokenStore {
  _FakeSecureTokenStore() : super(const FlutterSecureStorage());

  @override
  Future<String?> readToken() async => 'test-token';
}

class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository(this._user) : super(Dio());

  final UserMe _user;

  @override
  Future<UserMe> me() async => _user;
}

class _FakePushService extends PushService {
  _FakePushService() : super(Dio());

  @override
  Future<void> registerDeviceIfPossible() async {}
}

class _FakeMarketplaceRepository extends MarketplaceRepository {
  _FakeMarketplaceRepository(this.connections) : super(Dio());

  final List<ConnectionItem> connections;

  @override
  Future<List<ConnectionItem>> farmerConnections() async => connections;

  @override
  Future<void> patchConnection(int id, String status) async {}
}

final _farmerUser = UserMe(
  id: 1,
  phoneNumber: '+94770000001',
  role: 'farmer',
  subscriptionStatus: 'active',
  name: 'Amal',
  createdAt: DateTime.parse('2026-01-01T00:00:00Z'),
);

void main() {
  testWidgets('Farmer inbox shows buyer and Accept/Decline under AppTheme', (tester) async {
    tester.view.physicalSize = const Size(400, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWith((ref) => _FakeAuthRepository(_farmerUser)),
          secureTokenStoreProvider.overrideWith((ref) => _FakeSecureTokenStore()),
          pushServiceProvider.overrideWith((ref) => _FakePushService()),
          pendingConnectionsCountProvider.overrideWith((ref) async => 1),
          marketplaceRepositoryProvider.overrideWith(
            (ref) => _FakeMarketplaceRepository([_pendingConnection()]),
          ),
        ],
        child: MaterialApp(
          theme: AppTheme.light,
          home: const ConnectionsScreen(),
        ),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Tomato'), findsOneWidget);
    expect(find.textContaining('Buyer One'), findsOneWidget);
    expect(find.text('Accept'), findsOneWidget);
    expect(find.text('Decline'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
