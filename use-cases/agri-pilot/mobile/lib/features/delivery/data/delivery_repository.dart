import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

class DeliveryRepository {
  DeliveryRepository(this._dio);
  final Dio _dio;

  // Buyer
  Future<OrderCreateResult> createOrder({
    int? connectionId,
    int? listingId,
    required double quantityKg,
    required String fulfillmentMode,
    String? deliveryAddressLabel,
    double? deliveryLatitude,
    double? deliveryLongitude,
  }) async {
    final resp = await _dio.post('/api/buyer/orders', data: {
      if (connectionId != null) 'connection_id': connectionId,
      if (listingId != null) 'listing_id': listingId,
      'quantity_kg': quantityKg,
      'fulfillment_mode': fulfillmentMode,
      if (deliveryAddressLabel != null) 'delivery_address_label': deliveryAddressLabel,
      if (deliveryLatitude != null) 'delivery_latitude': deliveryLatitude,
      if (deliveryLongitude != null) 'delivery_longitude': deliveryLongitude,
    });
    return OrderCreateResult.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<List<OrderItem>> buyerOrders() async {
    final resp = await _dio.get('/api/buyer/orders');
    return (resp.data as List).map((e) => OrderItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<OrderTracking> tracking(int orderId) async {
    final resp = await _dio.get('/api/buyer/orders/$orderId/tracking');
    return OrderTracking.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<OrderItem> confirmHandoffBuyer(int orderId, String pin) async {
    final resp = await _dio.post('/api/buyer/orders/$orderId/confirm-handoff', data: {'pin': pin});
    return OrderItem.fromJson(resp.data as Map<String, dynamic>);
  }

  // Farmer
  Future<List<OrderItem>> farmerOrders() async {
    final resp = await _dio.get('/api/farmer/orders');
    return (resp.data as List).map((e) => OrderItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<OrderItem> farmerConfirm(int orderId, {
    required double quantityKg,
    String? pickupAddressLabel,
    double? pickupLatitude,
    double? pickupLongitude,
  }) async {
    final resp = await _dio.post('/api/farmer/orders/$orderId/confirm', data: {
      'confirmed_quantity_kg': quantityKg,
      if (pickupAddressLabel != null) 'pickup_address_label': pickupAddressLabel,
      if (pickupLatitude != null) 'pickup_latitude': pickupLatitude,
      if (pickupLongitude != null) 'pickup_longitude': pickupLongitude,
    });
    return OrderItem.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<OrderItem> farmerReject(int orderId, {String? reason}) async {
    final resp = await _dio.post('/api/farmer/orders/$orderId/reject', data: {'reason': reason});
    return OrderItem.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<OrderItem> farmerMarkReady(int orderId) async {
    final resp = await _dio.post('/api/farmer/orders/$orderId/ready');
    return OrderItem.fromJson(resp.data as Map<String, dynamic>);
  }

  // Rider
  Future<void> setOnline(bool online) async {
    await _dio.post('/api/rider/online', data: {'online': online});
  }

  Future<void> postLocation(double lat, double lon, {double? heading, double? accuracy}) async {
    await _dio.post('/api/rider/location', data: {
      'latitude': lat,
      'longitude': lon,
      if (heading != null) 'heading': heading,
      if (accuracy != null) 'accuracy_m': accuracy,
    });
  }

  Future<List<RiderJob>> availableJobs() async {
    final resp = await _dio.get('/api/rider/jobs');
    return (resp.data as List).map((e) => RiderJob.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> rejectJob(int orderId) async {
    await _dio.post('/api/rider/jobs/$orderId/reject');
  }

  Future<Map<String, dynamic>> acceptJob(
    int orderId, {
    double? latitude,
    double? longitude,
    double? accuracyM,
  }) async {
    final resp = await _dio.post('/api/rider/jobs/$orderId/accept', data: {
      if (latitude != null) 'latitude': latitude,
      if (longitude != null) 'longitude': longitude,
      if (accuracyM != null) 'accuracy_m': accuracyM,
    });
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>?> activeDelivery() async {
    final resp = await _dio.get('/api/rider/deliveries/active');
    if (resp.data == null) return null;
    return resp.data as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> updateDeliveryStatus(int deliveryId, String status) async {
    final resp = await _dio.post('/api/rider/deliveries/$deliveryId/status', data: {'status': status});
    return resp.data as Map<String, dynamic>;
  }

  Future<OrderItem> confirmHandoffRider(int orderId, String pin) async {
    final resp = await _dio.post('/api/rider/orders/$orderId/confirm-handoff', data: {'pin': pin});
    return OrderItem.fromJson(resp.data as Map<String, dynamic>);
  }
}

final deliveryRepositoryProvider = Provider<DeliveryRepository>((ref) {
  return DeliveryRepository(ref.watch(dioProvider));
});
