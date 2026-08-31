import 'package:dio/dio.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../network/dio_client.dart';

typedef OrderDeepLinkHandler = void Function(int orderId);

class PushService {
  PushService(this._dio);
  final Dio _dio;
  String? _fcmToken;
  static OrderDeepLinkHandler? _orderDeepLinkHandler;

  static Future<void> initialize() async {
    try {
      await Firebase.initializeApp();
    } catch (e) {
      debugPrint('Firebase init skipped: $e');
    }
  }

  static void registerOrderDeepLinkHandler(OrderDeepLinkHandler handler) {
    _orderDeepLinkHandler = handler;
  }

  Future<void> listenForNavigation() async {
    try {
      FirebaseMessaging.onMessageOpenedApp.listen((message) {
        _handleDeliveryPayload(message.data);
      });
      final initial = await FirebaseMessaging.instance.getInitialMessage();
      if (initial != null) {
        _handleDeliveryPayload(initial.data);
      }
    } catch (e) {
      debugPrint('FCM navigation listen skipped: $e');
    }
  }

  void _handleDeliveryPayload(Map<String, dynamic> data) {
    if (data['type'] != 'delivery_update') return;
    final orderIdRaw = data['order_id'];
    final orderId = orderIdRaw is int ? orderIdRaw : int.tryParse('$orderIdRaw');
    if (orderId != null) {
      _orderDeepLinkHandler?.call(orderId);
    }
  }

  Future<void> registerDeviceIfPossible() async {
    try {
      final token = await FirebaseMessaging.instance.getToken();
      if (token == null) return;
      _fcmToken = token;
      await _dio.post('/api/devices/register', data: {'fcm_token': token, 'platform': 'android'});
    } catch (e) {
      debugPrint('FCM register skipped: $e');
    }
  }

  Future<void> unregisterDeviceIfPossible() async {
    if (_fcmToken == null) return;
    try {
      await _dio.delete('/api/devices/unregister', queryParameters: {'fcm_token': _fcmToken});
    } catch (_) {}
    _fcmToken = null;
  }
}

final pushServiceProvider = Provider<PushService>((ref) {
  return PushService(ref.watch(dioProvider));
});
