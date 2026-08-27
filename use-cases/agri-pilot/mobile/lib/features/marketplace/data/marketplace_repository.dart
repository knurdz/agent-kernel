import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

class MarketplaceRepository {
  MarketplaceRepository(this._dio);
  final Dio _dio;

  Future<List<Listing>> farmerListings() async {
    final resp = await _dio.get('/api/farmer/listings');
    final items = resp.data['items'] as List<dynamic>;
    return items.map((e) => Listing.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<Listing> createListing({required String crop, required double qty, double? price}) async {
    final resp = await _dio.post('/api/farmer/listings', data: {
      'crop': crop,
      'quantity_kg': qty,
      if (price != null) 'price_per_kg': price,
    });
    return Listing.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<void> deleteListing(int id) async {
    await _dio.delete('/api/farmer/listings/$id');
  }

  Future<List<ConnectionItem>> farmerConnections() async {
    final resp = await _dio.get('/api/farmer/connections');
    return (resp.data as List<dynamic>).map((e) => ConnectionItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<void> patchConnection(int id, String status) async {
    await _dio.patch('/api/farmer/connections/$id', data: {'status': status});
  }

  Future<String> farmerContact(int connectionId) async {
    final resp = await _dio.get('/api/farmer/connections/$connectionId/contact');
    return resp.data['phone_number'] as String;
  }

  Future<List<Listing>> browse({String? crop, String? district}) async {
    final resp = await _dio.get('/api/buyer/listings', queryParameters: {
      if (crop != null && crop.isNotEmpty) 'crop': crop,
      if (district != null && district.isNotEmpty) 'district': district,
      'limit': 20,
    });
    return (resp.data['items'] as List<dynamic>).map((e) => Listing.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<List<Listing>> match({required String crop, String? district, double? qty}) async {
    final resp = await _dio.get('/api/buyer/match', queryParameters: {
      'crop': crop,
      if (district != null) 'district': district,
      if (qty != null) 'quantity_kg': qty,
    });
    return (resp.data['items'] as List<dynamic>)
        .map((e) => Listing.fromJson((e['listing'] as Map<String, dynamic>)))
        .toList();
  }

  Future<void> connect(int listingId, {String? message}) async {
    await _dio.post('/api/buyer/listings/$listingId/connect', data: {
      if (message != null) 'message': message,
    });
  }

  Future<List<ConnectionItem>> buyerConnections() async {
    final resp = await _dio.get('/api/buyer/connections');
    return (resp.data as List<dynamic>).map((e) => ConnectionItem.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<String> buyerContact(int connectionId) async {
    final resp = await _dio.get('/api/buyer/connections/$connectionId/contact');
    return resp.data['phone_number'] as String;
  }

  Future<PublicConfig> publicConfig() async {
    final resp = await _dio.get('/api/config/public');
    return PublicConfig.fromJson(resp.data as Map<String, dynamic>);
  }
}

final marketplaceRepositoryProvider = Provider<MarketplaceRepository>(
  (ref) => MarketplaceRepository(ref.watch(dioProvider)),
);
