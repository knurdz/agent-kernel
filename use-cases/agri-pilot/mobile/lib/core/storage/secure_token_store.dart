import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SecureTokenStore {
  SecureTokenStore(this._storage);
  final FlutterSecureStorage _storage;
  static const _tokenKey = 'jwt_token';

  Future<void> saveToken(String token) => _storage.write(key: _tokenKey, value: token);
  Future<String?> readToken() => _storage.read(key: _tokenKey);
  Future<void> clearToken() => _storage.delete(key: _tokenKey);
}

final secureTokenStoreProvider = Provider<SecureTokenStore>(
  (ref) => SecureTokenStore(const FlutterSecureStorage()),
);
