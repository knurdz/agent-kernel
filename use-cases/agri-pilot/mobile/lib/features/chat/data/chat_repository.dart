import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/dio_client.dart';
import '../../auth/domain/models.dart';

class ChatRepository {
  ChatRepository(this._dio);
  final Dio _dio;

  Future<String> sendText(String prompt) async {
    final resp = await _dio.post('/api/v1/chat', data: {'prompt': prompt, 'session_id': 'ignored', 'agent': 'triage'});
    return resp.data['result'] as String;
  }

  Future<String> sendPhoto(String prompt, File image) async {
    final form = FormData.fromMap({
      'prompt': prompt,
      'session_id': 'ignored',
      'agent': 'triage',
      'images': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
    });
    final resp = await _dio.post('/api/v1/chat-multipart', data: form);
    return resp.data['result'] as String;
  }

  Future<List<ChatMessage>> history() async {
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
  }
}

final chatRepositoryProvider = Provider<ChatRepository>((ref) => ChatRepository(ref.watch(dioProvider)));
