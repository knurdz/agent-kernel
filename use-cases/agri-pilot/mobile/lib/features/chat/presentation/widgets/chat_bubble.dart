import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

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
    final color = isUser ? theme.colorScheme.onPrimaryContainer : theme.colorScheme.onSurface;

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
                child: isUser
                    ? Text(
                        text,
                        style: theme.textTheme.bodyMedium?.copyWith(color: color),
                      )
                    : MarkdownBody(
                        data: text,
                        selectable: true,
                        shrinkWrap: true,
                        softLineBreak: true,
                        styleSheet: _advisorMarkdownStyle(theme, color),
                        onTapLink: (label, href, title) => _openLink(href),
                      ),
              ),
          ],
        ),
      ),
    );
  }
}

MarkdownStyleSheet _advisorMarkdownStyle(ThemeData theme, Color color) {
  final base = theme.textTheme.bodyMedium?.copyWith(color: color, height: 1.45);
  return MarkdownStyleSheet.fromTheme(theme).copyWith(
    p: base,
    pPadding: EdgeInsets.zero,
    h1: theme.textTheme.titleMedium?.copyWith(color: color, fontWeight: FontWeight.w700),
    h2: theme.textTheme.titleSmall?.copyWith(color: color, fontWeight: FontWeight.w700),
    h3: theme.textTheme.titleSmall?.copyWith(color: color, fontWeight: FontWeight.w600),
    h1Padding: const EdgeInsets.only(top: 4, bottom: 4),
    h2Padding: const EdgeInsets.only(top: 4, bottom: 2),
    h3Padding: const EdgeInsets.only(top: 4, bottom: 2),
    strong: base?.copyWith(fontWeight: FontWeight.w700),
    em: base?.copyWith(fontStyle: FontStyle.italic),
    listBullet: base,
    listIndent: 20,
    blockSpacing: 8,
    blockquotePadding: const EdgeInsets.fromLTRB(12, 4, 4, 4),
    blockquoteDecoration: BoxDecoration(
      border: Border(left: BorderSide(color: color.withValues(alpha: 0.35), width: 3)),
    ),
    code: theme.textTheme.bodySmall?.copyWith(
      color: color,
      fontFamily: 'monospace',
      backgroundColor: theme.colorScheme.surfaceContainerHigh,
    ),
    codeblockPadding: const EdgeInsets.all(10),
    codeblockDecoration: BoxDecoration(
      color: theme.colorScheme.surfaceContainerHigh,
      borderRadius: BorderRadius.circular(8),
    ),
    a: base?.copyWith(
      color: theme.colorScheme.primary,
      decoration: TextDecoration.underline,
    ),
    tableHead: base?.copyWith(fontWeight: FontWeight.w700),
    tableBody: base,
  );
}

Future<void> _openLink(String? href) async {
  if (href == null || href.isEmpty) return;
  final uri = Uri.tryParse(href);
  if (uri == null) return;
  await launchUrl(uri, mode: LaunchMode.externalApplication);
}
