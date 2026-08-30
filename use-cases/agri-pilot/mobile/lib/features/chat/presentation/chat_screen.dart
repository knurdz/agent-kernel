import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/analysing_status.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/start_tracking_crop_banner.dart';
import '../../plants/data/plants_repository.dart';
import '../data/chat_repository.dart';
import 'widgets/chat_bubble.dart';

class _ChatBubble {
  const _ChatBubble({required this.role, required this.text, this.image});

  final String role;
  final String text;
  final File? image;
}

class ChatScreen extends ConsumerStatefulWidget {
  const ChatScreen({
    super.key,
    required this.sessionId,
    this.initialPrompt,
    this.threadName,
  });

  final String sessionId;
  final String? initialPrompt;
  final String? threadName;

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _messages = <_ChatBubble>[];
  var _loading = false;
  var _loadingWithPhoto = false;
  var _initialized = false;
  var _showTrackingBanner = false;
  var _sentFirstMessage = false;
  File? _pendingImage;

  static const _promptChips = [
    "What's wrong with my tomato leaves?",
    'When should I irrigate my crop?',
    'How do I treat early blight?',
  ];

  @override
  void initState() {
    super.initState();
    _loadHistory();
    _loadTrackingBanner();
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

  Future<void> _loadTrackingBanner() async {
    try {
      final plants = await ref.read(plantsRepositoryProvider).listPlants();
      if (mounted) setState(() => _showTrackingBanner = plants.isEmpty);
    } catch (_) {
      // Banner is optional; ignore load failures.
    }
  }

  Future<void> _loadHistory() async {
    try {
      final repo = ref.read(chatRepositoryProvider);
      final history = await repo.getMessages(widget.sessionId);
      setState(() {
        _messages.addAll(history.map((m) => _ChatBubble(role: m.role, text: m.content)));
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

  String _userBubbleText(String text, File? image) {
    if (image != null) {
      final trimmed = text.trim();
      if (trimmed.isEmpty || trimmed == 'Diagnose this crop') return '';
      return trimmed;
    }
    return text;
  }

  String? _threadNameForFirstMessage(String text) {
    if (_sentFirstMessage) return null;
    final preset = widget.threadName?.trim();
    if (preset != null && preset.isNotEmpty) return preset;
    final trimmed = text.trim();
    if (trimmed.isEmpty) return 'Crop photo';
    return trimmed.length > 48 ? '${trimmed.substring(0, 48)}…' : trimmed;
  }

  Future<void> _send({File? image, String? presetText}) async {
    final pending = image ?? _pendingImage;
    final text = presetText ?? _controller.text.trim();
    if (text.isEmpty && pending == null) return;
    final prompt = text.isEmpty ? 'Diagnose this crop' : text;
    final threadName = _threadNameForFirstMessage(prompt);
    setState(() {
      _loading = true;
      _loadingWithPhoto = pending != null;
      _pendingImage = null;
      _messages.add(_ChatBubble(role: 'user', text: _userBubbleText(prompt, pending), image: pending));
    });
    if (presetText == null) _controller.clear();
    _scrollToBottom();
    try {
      final repo = ref.read(chatRepositoryProvider);
      final reply = pending != null
          ? await repo.sendPhoto(
              prompt,
              pending,
              sessionId: widget.sessionId,
              threadName: threadName,
            )
          : await repo.sendText(
              prompt,
              sessionId: widget.sessionId,
              threadName: threadName,
            );
      if (mounted) setState(() => _sentFirstMessage = true);
      setState(() => _messages.add(_ChatBubble(role: 'assistant', text: reply)));
    } catch (e) {
      setState(() => _messages.add(_ChatBubble(
            role: 'assistant',
            text: apiErrorMessage(e),
          )));
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _loadingWithPhoto = false;
        });
        _scrollToBottom();
      }
    }
  }

  Future<void> _pickPhoto(ImageSource source) async {
    final picker = ImagePicker();
    final file = await picker.pickImage(source: source, maxWidth: 1920, imageQuality: 85);
    if (file != null) setState(() => _pendingImage = File(file.path));
  }

  void _clearPendingImage() {
    setState(() => _pendingImage = null);
  }

  bool get _canSend => !_loading && (_controller.text.trim().isNotEmpty || _pendingImage != null);

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
    final itemCount = _messages.length + (_loading ? 1 : 0);

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.threadName ?? 'Conversation'),
      ),
      body: Column(
        children: [
          if (_showTrackingBanner) const StartTrackingCropBanner(),
          Expanded(
            child: !_initialized
                ? const Center(child: CircularProgressIndicator())
                : _messages.isEmpty && !_loading
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
                        itemCount: itemCount,
                        itemBuilder: (_, i) {
                          if (_loading && i == itemCount - 1) {
                            return Align(
                              alignment: Alignment.centerLeft,
                              child: Container(
                                constraints: BoxConstraints(
                                  maxWidth: MediaQuery.sizeOf(context).width * 0.78,
                                ),
                                margin: const EdgeInsets.symmetric(vertical: 4),
                                decoration: BoxDecoration(
                                  color: theme.colorScheme.surfaceContainerHighest,
                                  borderRadius: const BorderRadius.only(
                                    topLeft: Radius.circular(16),
                                    topRight: Radius.circular(16),
                                    bottomLeft: Radius.circular(4),
                                    bottomRight: Radius.circular(16),
                                  ),
                                ),
                                child: _loadingWithPhoto
                                    ? const AnalysingStatus.photo(compact: true)
                                    : const AnalysingStatus.text(compact: true),
                              ),
                            );
                          }
                          return ChatBubble(
                            role: _messages[i].role,
                            text: _messages[i].text,
                            image: _messages[i].image,
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
          if (_pendingImage != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 4),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Image.file(
                        _pendingImage!,
                        width: 72,
                        height: 72,
                        fit: BoxFit.cover,
                      ),
                    ),
                    Positioned(
                      top: -8,
                      right: -8,
                      child: IconButton.filledTonal(
                        visualDensity: VisualDensity.compact,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(minWidth: 28, minHeight: 28),
                        iconSize: 16,
                        onPressed: _loading ? null : _clearPendingImage,
                        icon: const Icon(Icons.close),
                      ),
                    ),
                  ],
                ),
              ),
            ),
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
                      onChanged: (_) => setState(() {}),
                      decoration: InputDecoration(
                        hintText: _pendingImage != null
                            ? 'Add a message (optional)…'
                            : 'Ask about crops, weather...',
                        filled: true,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(24),
                          borderSide: BorderSide.none,
                        ),
                      ),
                      textInputAction: TextInputAction.send,
                      onSubmitted: _canSend ? (_) => _send() : null,
                    ),
                  ),
                  const SizedBox(width: 8),
                  FilledButton(
                    onPressed: _canSend ? () => _send() : null,
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
