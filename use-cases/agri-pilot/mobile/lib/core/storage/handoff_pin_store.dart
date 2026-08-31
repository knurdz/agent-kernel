import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists buyer handoff PINs locally (server stores hash only).
class HandoffPinStore {
  HandoffPinStore({FlutterSecureStorage? storage}) : _storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage _storage;
  static const _prefix = 'handoff_pin_order_';

  Future<void> save(int orderId, String pin) async {
    await _storage.write(key: '$_prefix$orderId', value: pin);
  }

  Future<String?> read(int orderId) => _storage.read(key: '$_prefix$orderId');

  Future<void> delete(int orderId) async {
    await _storage.delete(key: '$_prefix$orderId');
  }
}
