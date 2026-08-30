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
      repo.sendText('hello', sessionId: 'agri:user:1:t:abc'),
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

    await expectLater(
      repo.sendText('blight?', sessionId: 'agri:user:1:t:abc'),
      completion('Try neem oil spray.'),
    );
  });

  test('sendText accepts fallback prompt for image-only style requests', () async {
    when(() => dio.post(any(), data: any(named: 'data'))).thenAnswer(
      (_) async => Response(
        requestOptions: RequestOptions(path: '/api/v1/chat'),
        data: {'result': 'Looks like blight.'},
      ),
    );

    await expectLater(
      repo.sendText('Diagnose this crop', sessionId: 'agri:user:1:t:abc'),
      completion('Looks like blight.'),
    );
  });

  test('newThreadSessionId is user-owned', () {
    final sessionId = newThreadSessionId(42);
    expect(sessionId.startsWith('agri:user:42:t:'), isTrue);
  });
}
