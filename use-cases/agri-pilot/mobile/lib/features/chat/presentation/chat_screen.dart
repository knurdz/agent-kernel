import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../data/chat_repository.dart';

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({super.key, this.initialPrompt});

  final String? initialPrompt;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _messages = <({String role, String text})>[];
  var _loading = false;
  var _initialized = false;

  static const _promptChips = [
    "What's wrong with my tomato leaves?",
    'When should I irrigate my crop?',
    'How do I treat early blight?',
  ];

  @override
  void initState() {
    super.initState();
    _loadHistory();
    final prompt = widget.initialPrompt;
    if (prompt != null && prompt.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _send(presetText: prompt));
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadHistory() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final history = await repo.history();
      setState(() {
        _messages.addAll(history.map((m) => (role: m.role, text: m.content)));
        _initialized = true;
      });
      _scrollToBottom();
    } catch (_) {
      setState(() => _initialized = true);
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _send({File? image, String? presetText}) async {
    final text = presetText ?? _controller.text.trim();
    if (text.isEmpty && image == null) return;
    setState(() {
      _loading = true;
      _messages.add((role: 'user', text: image != null ? '$text [photo]' : text));
    });
    if (presetText == null) _controller.clear();
    _scrollToBottom();
    try {
      final repo = ref.read(chatRepositoryProvider);
      final reply = image != null
          ? await repo.sendPhoto(text.isEmpty ? 'Diagnose this crop' : text, image)
          : await repo.sendText(text);
      setState(() => _messages.add((role: 'assistant', text: reply)));
    } catch (e) {
      setState(() => _messages.add((
            role: 'assistant',
            text: e is ApiException ? e.message : 'Error sending message',
          )));
    } finally {
      if (mounted) {
        setState(() => _loading = false);
        _scrollToBottom();
      }
    }
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: source, maxWidth: 1920, imageQuality: 85);
    if (file != null) await _send(image: File(file.path));
  }

  void _showAttachOptions() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_camera_outlined),
              title: const Text('Take photo'),
              onTap: () {
                Navigator.pop(ctx);
                _pickPhoto(ImageSource.camera);
              },
            ),
            ListTile(
              leading: const Icon(Icons.photo_library_outlined),
              title: const Text('Choose from gallery'),
              onTap: () {
                Navigator.pop(ctx);
                _pickPhoto(ImageSource.gallery);
              },
            ),
            ListTile(
              leading: const Icon(Icons.document_scanner_outlined),
              title: const Text('Quick scan (structured result)'),
              onTap: () {
                Navigator.pop(ctx);
                context.push('/chat/scan');
              },
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AgriPilot Advisor'),
      ),
      body: Column(
        children: [
          Expanded(
            child: !_initialized
                ? const Center(child: CircularProgressIndicator())
                : _messages.isEmpty
                    ? EmptyState(
                        icon: Icons.smart_toy_outlined,
                        title: 'Your AI farming advisor',
                        subtitle: 'Ask about crops, diseases, weather, or send a photo for diagnosis.',
                        actionLabel: 'Diagnose a crop',
                        onAction: _showAttachOptions,
                      )
                    : ListView.builder(
                        controller: _scrollController,
                        padding: const EdgeInsets.all(16),
                        itemCount: _messages.length,
                        itemBuilder: (_, i) {
                          final m = _messages[i];
                          final isUser = m.role == 'user';
                          return Align(
                            alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                            child: Container(
                              constraints: BoxConstraints(
                                maxWidth: MediaQuery.sizeOf(context).width * 0.78,
                              ),
                              margin: const EdgeInsets.symmetric(vertical: 4),
                              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                              decoration: BoxDecoration(
                                color: isUser
                                    ? theme.colorScheme.primaryContainer
                                    : theme.colorScheme.surfaceContainerHighest,
                                borderRadius: BorderRadius.only(
                                  topLeft: const Radius.circular(16),
                                  topRight: const Radius.circular(16),
                                  bottomLeft: Radius.circular(isUser ? 16 : 4),
                                  bottomRight: Radius.circular(isUser ? 4 : 16),
                                ),
                              ),
                              child: Text(
                                m.text,
                                style: theme.textTheme.bodyMedium?.copyWith(
                                  color: isUser
                                      ? theme.colorScheme.onPrimaryContainer
                                      : theme.colorScheme.onSurface,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
          ),
          if (_messages.isEmpty && _initialized) ...[
            SizedBox(
              height: 44,
              child: ListView.separated(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                itemCount: _promptChips.length,
                separatorBuilder: (_, __) => const SizedBox(width: 8),
                itemBuilder: (_, i) => ActionChip(
                  label: Text(_promptChips[i]),
                  onPressed: _loading ? null : () => _send(presetText: _promptChips[i]),
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => context.push('/chat/scan'),
                      icon: const Icon(Icons.document_scanner_outlined, size: 18),
                      label: const Text('Quick scan'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () => context.go('/home/plants'),
                      icon: const Icon(Icons.eco_outlined, size: 18),
                      label: const Text('My plants'),
                    ),
                  ),
                ],
              ),
            ),
          ],
          if (_loading)
            LinearProgressIndicator(color: theme.colorScheme.primary),
          SafeArea(
            top: false,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  IconButton(
                    onPressed: _loading ? null : _showAttachOptions,
                    icon: const Icon(Icons.add_photo_alternate_outlined),
                  ),
                  Expanded(
                    child: TextField(
                      controller: _controller,
                      maxLines: 4,
                      minLines: 1,
                      decoration: InputDecoration(
                        hintText: 'Ask about crops, weather...',
                        filled: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide.none,
                        ),
                      ),
                      textInputAction: TextInputAction.send,
                      onSubmitted: _loading ? null : (_) => _send(),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _loading ? null : () => _send(),
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(48, 48),
                      padding: EdgeInsets.zero,
                      shape: const CircleBorder(),
                    ),
                    child: const Icon(Icons.send, size: 20),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
