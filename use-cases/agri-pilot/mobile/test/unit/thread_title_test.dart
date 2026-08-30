import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/features/chat/domain/thread_title.dart';

void main() {
  test('meaningful first prompt becomes the title', () {
    expect(
      deriveThreadTitle(prompt: "What's wrong with my tomato leaves?"),
      "What's wrong with my tomato leaves?",
    );
  });

  test('long prompts are truncated', () {
    final title = deriveThreadTitle(prompt: 'a' * 60);
    expect(title.length, 49);
    expect(title.endsWith('…'), isTrue);
  });

  test('generic photo prompt gets a unique timestamped title', () {
    final a = deriveThreadTitle(
      prompt: 'Diagnose this crop',
      hasPhoto: true,
      at: DateTime(2026, 8, 31, 14, 56),
    );
    final b = deriveThreadTitle(
      prompt: 'Diagnose this crop',
      hasPhoto: true,
      at: DateTime(2026, 8, 31, 15, 10),
    );
    expect(a, isNot(equals(b)));
    expect(a, contains('Crop photo'));
    expect(b, contains('Crop photo'));
  });

  test('generic conversation names are detected', () {
    expect(isGenericThreadTitle(null), isTrue);
    expect(isGenericThreadTitle(''), isTrue);
    expect(isGenericThreadTitle('Conversation'), isTrue);
    expect(isGenericThreadTitle('New conversation'), isTrue);
    expect(isGenericThreadTitle('Diagnose this crop'), isTrue);
    expect(isGenericThreadTitle('Tomato blight'), isFalse);
  });
}
