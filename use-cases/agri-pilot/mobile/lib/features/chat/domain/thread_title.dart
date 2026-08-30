import 'package:intl/intl.dart';

const _genericTitles = {
  'conversation',
  'new conversation',
  'diagnose this crop',
  'crop photo',
};

/// True when [name] is a placeholder rather than a real conversation title.
bool isGenericThreadTitle(String? name) {
  final trimmed = name?.trim() ?? '';
  if (trimmed.isEmpty) return true;
  return _genericTitles.contains(trimmed.toLowerCase());
}

/// A unique, human-readable title from the first message (or a photo fallback).
String deriveThreadTitle({
  required String prompt,
  bool hasPhoto = false,
  DateTime? at,
}) {
  final trimmed = prompt.trim();
  if (trimmed.isNotEmpty && !isGenericThreadTitle(trimmed)) {
    return trimmed.length > 48 ? '${trimmed.substring(0, 48)}…' : trimmed;
  }
  final stamp = DateFormat('MMM d, h:mm a').format(at ?? DateTime.now());
  if (hasPhoto) return 'Crop photo · $stamp';
  return 'Chat · $stamp';
}
