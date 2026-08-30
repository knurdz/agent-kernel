import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/core/network/dio_client.dart';

DioException _dioException({
  int? statusCode,
  dynamic data,
  DioExceptionType type = DioExceptionType.badResponse,
}) {
  return DioException(
    requestOptions: RequestOptions(path: '/api/auth/login'),
    response: statusCode != null
        ? Response(
            requestOptions: RequestOptions(path: '/api/auth/login'),
            statusCode: statusCode,
            data: data,
          )
        : null,
    type: type,
  );
}

void main() {
  group('ApiException.fromDio', () {
    test('maps 401 invalid credentials', () {
      final ex = ApiException.fromDio(_dioException(
        statusCode: 401,
        data: {'detail': 'invalid credentials'},
      ));
      expect(ex.message, 'Incorrect phone number or password.');
      expect(ex.statusCode, 401);
    });

    test('maps 409 phone already registered', () {
      final ex = ApiException.fromDio(_dioException(
        statusCode: 409,
        data: {'detail': 'phone already registered'},
      ));
      expect(ex.message, 'An account with this phone number already exists. Try logging in.');
    });

    test('formats 422 validation list', () {
      final ex = ApiException.fromDio(_dioException(
        statusCode: 422,
        data: {
          'detail': [
            {
              'loc': ['body', 'phone_number'],
              'msg': 'Value error, phone_number must be E.164, e.g. +94770000001',
              'type': 'value_error',
            },
          ],
        },
      ));
      expect(ex.message, 'Enter a phone number with country code, like +94771234567.');
    });

    test('maps short password from 422 list', () {
      final ex = ApiException.fromDio(_dioException(
        statusCode: 422,
        data: {
          'detail': [
            {
              'loc': ['body', 'password'],
              'msg': 'String should have at least 8 characters',
              'type': 'string_too_short',
            },
          ],
        },
      ));
      expect(ex.message, 'Password must be at least 8 characters.');
    });

    test('maps connection timeout', () {
      final ex = ApiException.fromDio(_dioException(type: DioExceptionType.connectionTimeout));
      expect(ex.message, 'The server took too long to respond. Try again.');
    });

    test('maps connection error', () {
      final ex = ApiException.fromDio(_dioException(type: DioExceptionType.connectionError));
      expect(ex.message, 'Cannot reach the server. Check your connection.');
    });

    test('falls back for unknown response body', () {
      final ex = ApiException.fromDio(_dioException(statusCode: 500, data: {'error': 'boom'}));
      expect(ex.message, 'Something went wrong. Please try again.');
    });
  });

  group('apiErrorMessage', () {
    test('unwraps ApiException', () {
      expect(apiErrorMessage(ApiException('Test message')), 'Test message');
    });

    test('converts DioException', () {
      final msg = apiErrorMessage(_dioException(
        statusCode: 401,
        data: {'detail': 'invalid credentials'},
      ));
      expect(msg, 'Incorrect phone number or password.');
    });

    test('falls back for unknown errors', () {
      expect(apiErrorMessage(Exception('fail')), 'Something went wrong. Please try again.');
    });
  });
}
