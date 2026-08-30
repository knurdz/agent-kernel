import 'dart:async';

import 'package:flutter/material.dart';

/// Rotating status copy shown while the backend analyses a photo or composes a reply.
class AnalysingStatus extends StatefulWidget {
  const AnalysingStatus({
    super.key,
    required this.messages,
    this.interval = const Duration(milliseconds: 2500),
    this.compact = false,
  });

  const AnalysingStatus.photo({super.key, this.interval = const Duration(milliseconds: 2500), this.compact = false})
      : messages = const [
          'Looking at your crop…',
          'Checking photo quality…',
          'Running disease analysis…',
          'Almost done…',
        ];

  const AnalysingStatus.text({super.key, this.interval = const Duration(milliseconds: 2500), this.compact = false})
      : messages = const [
          'Thinking about your question…',
          'Checking crop advice…',
          'Putting a reply together…',
        ];

  final List<String> messages;
  final Duration interval;
  final bool compact;

  @override
  State<AnalysingStatus> createState() => _AnalysingStatusState();
}

class _AnalysingStatusState extends State<AnalysingStatus> {
  var _index = 0;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    if (widget.messages.length > 1) {
      _timer = Timer.periodic(widget.interval, (_) {
        if (!mounted) return;
        setState(() => _index = (_index + 1) % widget.messages.length);
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final message = widget.messages.isEmpty ? 'Analysing…' : widget.messages[_index % widget.messages.length];
    final spinnerSize = widget.compact ? 16.0 : 20.0;

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: widget.compact ? 8 : 12,
        vertical: widget.compact ? 6 : 10,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          SizedBox(
            width: spinnerSize,
            height: spinnerSize,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: theme.colorScheme.primary,
            ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: AnimatedSwitcher(
              duration: const Duration(milliseconds: 300),
              child: Text(
                message,
                key: ValueKey(message),
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
