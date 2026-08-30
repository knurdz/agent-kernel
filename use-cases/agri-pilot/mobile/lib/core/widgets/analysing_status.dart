import 'package:flutter/material.dart';

/// Static status copy shown while the backend analyses a photo or composes a reply.
class AnalysingStatus extends StatelessWidget {
  const AnalysingStatus({
    super.key,
    required this.message,
    this.compact = false,
  });

  const AnalysingStatus.photo({super.key, this.compact = false}) : message = 'Analysing crop…';

  const AnalysingStatus.text({super.key, this.compact = false}) : message = 'Thinking…';

  final String message;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final spinnerSize = compact ? 16.0 : 20.0;

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 12,
        vertical: compact ? 6 : 10,
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
            child: Text(
              message,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
                fontStyle: FontStyle.italic,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
