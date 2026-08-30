import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

String parseChatResult(dynamic data) {
  if (data is Map) {
    final result = data['result'];
    if (result == null) return 'No reply received. Please try again.';
    return result.toString();
  }
  return 'No reply received. Please try again.';
}

class ChatRepository {
  ChatRepository(this._dio);
  final Dio _dio;

  Future<String> sendText(String prompt) async {
    try {
      final resp = await _dio.post(
        '/api/v1/chat',
        data: {'prompt': prompt, 'session_id': 'ignored', 'agent': 'triage'},
      );
      return parseChatResult(resp.data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<String> sendPhoto(String prompt, File image) async {
    try {
      final form = FormData.fromMap({
        'prompt': prompt,
        'session_id': 'ignored',
        'agent': 'triage',
        'images': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
      });
      final resp = await _dio.post('/api/v1/chat-multipart', data: form);
      return parseChatResult(resp.data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<List<ChatMessage>> history() async {
    try {
      final resp = await _dio.get('/api/v1/threads');
      final threads = resp.data['threads'] as List<dynamic>;
      if (threads.isEmpty) return [];
      final sessionId = threads.first['session_id'] as String;
      final detail = await _dio.get('/api/v1/threads/$sessionId');
      final messages = detail.data['messages'] as List<dynamic>? ?? [];
      return messages
          .map(
            (m) => ChatMessage(
              role: m['role'] as String,
              content: m['content'] as String,
              createdAt: DateTime.tryParse(m['created_at'] as String? ?? '') ?? DateTime.now(),
            ),
          )
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }
}

final chatRepositoryProvider = Provider<ChatRepository>((ref) => ChatRepository(ref.watch(dioProvider)));
