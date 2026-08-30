import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:agripilot_mobile/core/network/dio_client.dart';
import 'package:agripilot_mobile/features/chat/data/chat_repository.dart';

class _MockDio extends Mock implements Dio {}

void main() {
  late _MockDio dio;
  late ChatRepository repo;

  setUp(() {
    dio = _MockDio();
    repo = ChatRepository(dio);
  });

  test('sendText wraps DioException as ApiException', () async {
    when(() => dio.post(any(), data: any(named: 'data'))).thenThrow(
      DioException(
        requestOptions: RequestOptions(path: '/api/v1/chat'),
        response: Response(
          requestOptions: RequestOptions(path: '/api/v1/chat'),
          statusCode: 500,
          data: {'detail': 'server error'},
        ),
        type: DioExceptionType.badResponse,
      ),
    );

    expect(
      repo.sendText('hello'),
      throwsA(isA<ApiException>()),
    );
  });

  test('sendText returns parsed result on success', () async {
    when(() => dio.post(any(), data: any(named: 'data'))).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/chat'),
        data: {'result': 'Try neem oil spray.'},
      ),
    );

    await expectLater(repo.sendText('blight?'), completion('Try neem oil spray.'));
  });
}
