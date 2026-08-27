import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/dio_client.dart';
import '../data/chat_repository.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _messages = <({String role, String text})>[];
  var _loading = false;
  var _initialized = false;

  @override
  void initState() {
    super.initState();
    _loadHistory();
  }

  Future<void> _loadHistory() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final history = await repo.history();
      setState(() {
        _messages.addAll(history.map((m) => (role: m.role, text: m.content)));
        _initialized = true;
      });
    } catch (_) {
      setState(() => _initialized = true);
    }
  }

  Future<void> _send({File? image}) async {
    final text = _controller.text.trim();
    if (text.isEmpty && image == null) return;
    setState(() {
      _loading = true;
      _messages.add((role: 'user', text: image != null ? '$text [photo]' : text));
    });
    _controller.clear();
    try {
      final repo = ref.read(chatRepositoryProvider);
      final reply = image != null ? await repo.sendPhoto(text.isEmpty ? 'Diagnose this crop' : text, image) : await repo.sendText(text);
      setState(() => _messages.add((role: 'assistant', text: reply)));
    } catch (e) {
      setState(() => _messages.add((role: 'assistant', text: e is ApiException ? e.message : 'Error sending message')));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickPhoto() async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: ImageSource.gallery, maxWidth: 1920, imageQuality: 85);
    if (file != null) await _send(image: File(file.path));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('AgriPilot Agent'), leading: BackButton(onPressed: () => context.pop())),
      body: Column(
        children: [
          Expanded(
            child: !_initialized
                ? const Center(child: CircularProgressIndicator())
                : ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) {
                      final m = _messages[i];
                      final isUser = m.role == 'user';
                      return Align(
                        alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                        child: Container(
                          margin: const EdgeInsets.symmetric(vertical: 4),
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: isUser ? Colors.green.shade100 : Colors.grey.shade200,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Text(m.text),
                        ),
                      );
                    },
                  ),
          ),
          if (_loading) const LinearProgressIndicator(),
          Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                IconButton(onPressed: _loading ? null : _pickPhoto, icon: const Icon(Icons.photo)),
                Expanded(child: TextField(controller: _controller, decoration: const InputDecoration(hintText: 'Ask about crops, weather...'))),
                IconButton(onPressed: _loading ? null : () => _send(), icon: const Icon(Icons.send)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
