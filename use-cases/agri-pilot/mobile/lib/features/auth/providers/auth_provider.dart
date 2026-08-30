import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/notifications/push_service.dart';
import '../../../core/storage/secure_token_store.dart';
import '../data/auth_repository.dart';
import '../domain/models.dart';

class AuthState {
  const AuthState({this.user, this.loading = false, this.error});
  final UserMe? user;
  final bool loading;
  final String? error;

  AuthState copyWith({UserMe? user, bool? loading, String? error}) =>
      AuthState(user: user ?? this.user, loading: loading ?? this.loading, error: error);
}

class AuthController extends StateNotifier<AsyncValue<UserMe?>> {
  AuthController(this._repo, this._tokenStore, this._push) : super(const AsyncLoading()) {
    _bootstrap();
  }

  final AuthRepository _repo;
  final SecureTokenStore _tokenStore;
  final PushService _push;

  Future<void> _bootstrap() async {
    final token = await _tokenStore.readToken();
    if (token == null) {
      state = const AsyncData(null);
      return;
    }
    try {
      final user = await _repo.me();
      state = AsyncData(user);
      await _push.registerDeviceIfPossible();
    } catch (_) {
      await _tokenStore.clearToken();
      state = const AsyncData(null);
    }
  }

  Future<void> login(String phone, String password) async {
    try {
      final token = await _repo.login(phone: phone, password: password);
      await _tokenStore.saveToken(token);
      final user = await _repo.me();
      state = AsyncData(user);
      await _push.registerDeviceIfPossible();
    } catch (e) {
      state = const AsyncData(null);
      rethrow;
    }
  }

  Future<void> signup({
    required String role,
    required String phone,
    required String password,
    required String name,
    String? district,
    bool? hasVehicle,
  }) async {
    await _repo.signup(
      role: role,
      phone: phone,
      password: password,
      name: name,
      district: district,
      hasVehicle: hasVehicle,
    );
    await login(phone, password);
  }

  Future<void> logout() async {
    await _push.unregisterDeviceIfPossible();
    await _tokenStore.clearToken();
    state = const AsyncData(null);
  }

  Future<void> refresh() async {
    final user = await _repo.me();
    state = AsyncData(user);
  }
}

final authControllerProvider = StateNotifierProvider<AuthController, AsyncValue<UserMe?>>((ref) {
  return AuthController(
    ref.watch(authRepositoryProvider),
    ref.watch(secureTokenStoreProvider),
    ref.watch(pushServiceProvider),
  );
});
