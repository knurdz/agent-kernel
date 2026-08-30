import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

class PlantsRepository {
  PlantsRepository(this._dio);
  final Dio _dio;

  Future<ScanResult> scanPhoto(File image, {String? crop}) async {
    final form = FormData.fromMap({
      if (crop != null && crop.isNotEmpty) 'crop': crop,
      'image': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
    });
    final resp = await _dio.post('/api/farmer/scans', data: form);
    return ScanResult.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<List<PlantSummary>> listPlants() async {
    final resp = await _dio.get('/api/farmer/plants');
    final items = resp.data['items'] as List<dynamic>;
    return items.map((e) => PlantSummary.fromJson(e as Map<String, dynamic>)).toList();
  }

  Future<PlantSummary> createPlant({required String crop, String? name, int? listingId}) async {
    final resp = await _dio.post('/api/farmer/plants', data: {
      'crop': crop,
      if (name != null && name.isNotEmpty) 'name': name,
      if (listingId != null) 'listing_id': listingId,
    });
    return PlantSummary.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<PlantDetail> getPlant(int id) async {
    final resp = await _dio.get('/api/farmer/plants/$id');
    return PlantDetail.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<PlantObservation> addObservation(int plantId, File image) async {
    final form = FormData.fromMap({
      'image': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
    });
    final resp = await _dio.post('/api/farmer/plants/$plantId/observations', data: form);
    return PlantObservation.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<PlantSummary> importFromListing(int listingId) async {
    final resp = await _dio.post('/api/farmer/listings/$listingId/import-plant');
    return PlantSummary.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<ListingInsights> listingInsights(int listingId) async {
    final resp = await _dio.get('/api/buyer/listings/$listingId/insights');
    return ListingInsights.fromJson(resp.data as Map<String, dynamic>);
  }
}

final plantsRepositoryProvider = Provider<PlantsRepository>((ref) => PlantsRepository(ref.watch(dioProvider)));
