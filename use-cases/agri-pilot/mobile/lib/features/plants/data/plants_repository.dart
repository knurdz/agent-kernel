import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

class PlantsRepository {
  PlantsRepository(this._dio);
  final Dio _dio;

  Future<ScanResult> scanPhoto(File image, {String? crop}) async {
    try {
      final form = FormData.fromMap({
        if (crop != null && crop.isNotEmpty) 'crop': crop,
        'image': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
      });
      final resp = await _dio.post('/api/farmer/scans', data: form);
      return ScanResult.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<List<PlantSummary>> listPlants() async {
    try {
      final resp = await _dio.get('/api/farmer/plants');
      final items = resp.data['items'] as List<dynamic>;
      return items.map((e) => PlantSummary.fromJson(e as Map<String, dynamic>)).toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<PlantSummary> createPlant({required String crop, String? name, int? listingId}) async {
    try {
      final resp = await _dio.post('/api/farmer/plants', data: {
        'crop': crop,
        if (name != null && name.isNotEmpty) 'name': name,
        if (listingId != null) 'listing_id': listingId,
      });
      return PlantSummary.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<PlantDetail> getPlant(int id) async {
    try {
      final resp = await _dio.get('/api/farmer/plants/$id');
      return PlantDetail.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<PlantObservation> addObservation(int plantId, File image) async {
    try {
      final form = FormData.fromMap({
        'image': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
      });
      final resp = await _dio.post('/api/farmer/plants/$plantId/observations', data: form);
      return PlantObservation.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<PlantSummary> importFromListing(int listingId) async {
    try {
      final resp = await _dio.post('/api/farmer/listings/$listingId/import-plant');
      return PlantSummary.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<ListingInsights> listingInsights(int listingId) async {
    try {
      final resp = await _dio.get('/api/buyer/listings/$listingId/insights');
      return ListingInsights.fromJson(resp.data as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}

final plantsRepositoryProvider = Provider<PlantsRepository>((ref) => PlantsRepository(ref.watch(dioProvider)));
