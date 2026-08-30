import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../config/env.dart';
import '../storage/secure_token_store.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;

  static ApiException fromDio(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return ApiException(
          'The server took too long to respond. Try again.',
          statusCode: e.response?.statusCode,
        );
      case DioExceptionType.connectionError:
        return ApiException(
          'Cannot reach the server. Check your connection.',
          statusCode: e.response?.statusCode,
        );
      default:
        break;
    }

    final data = e.response?.data;
    if (data is Map && data['detail'] != null) {
      final raw = _formatDetail(data['detail']);
      return ApiException(_mapUserMessage(raw), statusCode: e.response?.statusCode);
    }

    return ApiException('Something went wrong. Please try again.', statusCode: e.response?.statusCode);
  }

  static String _formatDetail(dynamic detail) {
    if (detail is String) return detail;
    if (detail is List) {
      final messages = detail.map((item) {
        if (item is Map) {
          var msg = item['msg']?.toString() ?? '';
          if (msg.startsWith('Value error, ')) {
            msg = msg.substring('Value error, '.length);
          }
          return msg;
        }
        return item.toString();
      }).where((m) => m.isNotEmpty);
      return messages.join(' ');
    }
    return detail.toString();
  }

  static String _mapUserMessage(String detail) {
    final lower = detail.toLowerCase();

    if (lower.contains('invalid credentials')) {
      return 'Incorrect phone number or password.';
    }
    if (detail.contains('phone already registered')) {
      return 'An account with this phone number already exists. Try logging in.';
    }
    if (detail.contains('E.164') || detail.contains('phone_number must be')) {
      return 'Enter a phone number with country code, like +94771234567.';
    }
    if (lower.contains('at least 8') ||
        lower.contains('string should have at least 8') ||
        lower.contains('ensure this value has at least 8')) {
      return 'Password must be at least 8 characters.';
    }
    if (lower.contains('field required') || (lower.contains('name') && lower.contains('required'))) {
      return 'Please fill in all required fields.';
    }
    if (detail.length <= 160 && !detail.contains('DioException')) {
      return detail;
    }
    return 'Something went wrong. Please try again.';
  }
}

String apiErrorMessage(Object e) {
  if (e is ApiException) return e.message;
  if (e is DioException) return ApiException.fromDio(e).message;
  return 'Something went wrong. Please try again.';
}

final dioProvider = Provider<Dio>((ref) {
  final tokenStore = ref.watch(secureTokenStoreProvider);
  final dio = Dio(
    BaseOptions(
      baseUrl: Env.apiBaseUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 180),
      headers: {'Content-Type': 'application/json'},
    ),
  );
  dio.interceptors.add(
    InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await tokenStore.readToken();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) {
        final path = error.requestOptions.path;
        final isAuthAttempt = path.contains('/api/auth/login') || path.contains('/api/auth/signup');
        if (error.response?.statusCode == 401 && !isAuthAttempt) {
          tokenStore.clearToken();
        }
        handler.next(error);
      },
    ),
  );
  return dio;
});
