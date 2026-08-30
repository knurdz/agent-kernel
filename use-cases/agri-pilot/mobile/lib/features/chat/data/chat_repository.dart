import 'dart:io';
import 'dart:math';

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

DateTime _parseMessageTime(Map<dynamic, dynamic> message) {
  final raw = message['timestamp'] ?? message['created_at'];
  if (raw is String) {
    return DateTime.tryParse(raw) ?? DateTime.now();
  }
  return DateTime.now();
}

String newThreadSessionId(int userId) {
  final suffix = '${DateTime.now().millisecondsSinceEpoch}-${Random().nextInt(0x7fffffff)}';
  return 'agri:user:$userId:t:$suffix';
}

class ChatRepository {
  ChatRepository(this._dio);
  final Dio _dio;

  Future<List<ThreadSummary>> listThreads() async {
    try {
      final resp = await _dio.get('/api/v1/threads');
      final threads = resp.data['threads'] as List<dynamic>? ?? [];
      return threads.map((t) => ThreadSummary.fromJson(t as Map<String, dynamic>)).toList()
        ..sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<List<ChatMessage>> getMessages(String sessionId) async {
    try {
      final detail = await _dio.get('/api/v1/threads/$sessionId');
      final messages = detail.data['messages'] as List<dynamic>? ?? [];
      return messages
          .map(
            (m) => ChatMessage(
              role: m['role'] as String,
              content: m['content'] as String,
              createdAt: _parseMessageTime(m as Map<dynamic, dynamic>),
            ),
          )
          .toList();
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<String> sendText(
    String prompt, {
    required String sessionId,
    String? threadName,
  }) async {
    try {
      final resp = await _dio.post(
        '/api/v1/chat',
        data: {
          'prompt': prompt,
          'session_id': sessionId,
          'agent': 'triage',
          if (threadName != null && threadName.isNotEmpty) 'thread_name': threadName,
        },
      );
      return parseChatResult(resp.data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  Future<String> sendPhoto(
    String prompt,
    File image, {
    required String sessionId,
    String? threadName,
  }) async {
    try {
      final form = FormData.fromMap({
        'prompt': prompt,
        'session_id': sessionId,
        'agent': 'triage',
        if (threadName != null && threadName.isNotEmpty) 'thread_name': threadName,
        'images': await MultipartFile.fromFile(image.path, filename: 'crop.jpg'),
      });
      final resp = await _dio.post('/api/v1/chat-multipart', data: form);
      return parseChatResult(resp.data);
    } on DioException catch (e) {
      throw ApiException.fromDio(e);
    }
  }

  @Deprecated('Use listThreads and getMessages')
  Future<List<ChatMessage>> history() async {
    final threads = await listThreads();
    if (threads.isEmpty) return [];
    return getMessages(threads.first.sessionId);
  }
}

final chatRepositoryProvider = Provider<ChatRepository>((ref) => ChatRepository(ref.watch(dioProvider)));
