import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../domain/models.dart';

class AuthRepository {
  AuthRepository(this._dio);
  final Dio _dio;

  Future<void> signup({
    required String role,
    required String phone,
    required String password,
    required String name,
    String? district,
  }) async {
    await _dio.post('/api/auth/signup', data: {
      'role': role,
      'phone_number': phone,
      'password': password,
      'name': name,
      if (district != null) 'district': district,
    });
  }

  Future<String> login({required String phone, required String password}) async {
    final resp = await _dio.post('/api/auth/login', data: {
      'phone_number': phone,
      'password': password,
    });
    return resp.data['access_token'] as String;
  }

  Future<UserMe> me() async {
    final resp = await _dio.get('/api/auth/me');
    return UserMe.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<UserMe> updateProfile(Map<String, dynamic> body) async {
    final resp = await _dio.patch('/api/auth/me', data: body);
    return UserMe.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<ChannelsStatus> channels() async {
    final resp = await _dio.get('/api/auth/me/channels');
    return ChannelsStatus.fromJson(resp.data as Map<String, dynamic>);
  }

  Future<String> telegramLinkUrl() async {
    final resp = await _dio.post('/api/auth/me/channels/telegram/link-token');
    return resp.data['deep_link_url'] as String;
  }

  Future<void> unlinkTelegram() async {
    await _dio.delete('/api/auth/me/channels/telegram');
  }
}

final authRepositoryProvider = Provider<AuthRepository>((ref) => AuthRepository(ref.watch(dioProvider)));
