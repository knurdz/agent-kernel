import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import 'package:agripilot_mobile/app.dart';
import 'package:agripilot_mobile/core/notifications/push_service.dart';
import 'package:agripilot_mobile/core/shell/main_shell.dart';
import 'package:agripilot_mobile/core/storage/secure_token_store.dart';
import 'package:agripilot_mobile/features/auth/data/auth_repository.dart';
import 'package:agripilot_mobile/features/auth/domain/models.dart';
import 'package:agripilot_mobile/features/marketplace/data/marketplace_repository.dart';

final _farmerUser = UserMe(
  id: 1,
  phoneNumber: '+94770000001',
  role: 'farmer',
  subscriptionStatus: 'active',
  name: 'Amal',
  createdAt: DateTime.parse('2026-01-01T00:00:00Z'),
  profile: UserProfile(district: 'Kandy'),
);

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
  _FakeMarketplaceRepository() : super(Dio());

  @override
  Future<List<Listing>> farmerListings() async => [];

  @override
  Future<List<ConnectionItem>> farmerConnections() async => [];

  @override
  Future<List<ConnectionItem>> buyerConnections() async => [];
}

List<Override> _testOverrides(UserMe user) => [
      authRepositoryProvider.overrideWith((ref) => _FakeAuthRepository(user)),
      secureTokenStoreProvider.overrideWith((ref) => _FakeSecureTokenStore()),
      pushServiceProvider.overrideWith((ref) => _FakePushService()),
      pendingConnectionsCountProvider.overrideWith((ref) async => 0),
      marketplaceRepositoryProvider.overrideWith((ref) => _FakeMarketplaceRepository()),
    ];

void main() {
  testWidgets('MainShell shows four labeled bottom nav destinations', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: _testOverrides(_farmerUser),
        child: const AgriPilotApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Advisor'), findsOneWidget);
    expect(find.text('Inbox'), findsOneWidget);
    expect(find.text('Me'), findsOneWidget);
  });

  testWidgets('Farmer home shows personalized greeting', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: _testOverrides(_farmerUser),
        child: const AgriPilotApp(),
      ),
    );

    await tester.pumpAndSettle();

    expect(find.text('Hi, Amal'), findsOneWidget);
    expect(find.text('Kandy'), findsOneWidget);
    expect(find.text('Ask AgriPilot'), findsOneWidget);
  });
}
