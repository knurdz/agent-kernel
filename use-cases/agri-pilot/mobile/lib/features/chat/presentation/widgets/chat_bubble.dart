import 'dart:io';

import 'package:flutter/material.dart';

class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.role,
    required this.text,
    this.image,
  });

  final String role;
  final String text;
  final File? image;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isUser = role == 'user';
    final hasImage = image != null;
    final hasText = text.isNotEmpty;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.78),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: EdgeInsets.fromLTRB(
          hasImage ? 8 : 14,
          hasImage ? 8 : 10,
          hasImage ? 8 : 14,
          hasImage ? 8 : 10,
        ),
        decoration: BoxDecoration(
          color: isUser ? theme.colorScheme.primaryContainer : theme.colorScheme.surfaceContainerHighest,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(isUser ? 16 : 4),
            bottomRight: Radius.circular(isUser ? 4 : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (hasImage)
              ClipRRect(
                borderRadius: BorderRadius.circular(12),
                child: Image.file(
                  image!,
                  height: 180,
                  width: double.infinity,
                  fit: BoxFit.cover,
                ),
              ),
            if (hasText)
              Padding(
                padding: EdgeInsets.only(top: hasImage ? 8 : 0, left: hasImage ? 6 : 0, right: hasImage ? 6 : 0),
                child: Text(
                  text,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: isUser ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
