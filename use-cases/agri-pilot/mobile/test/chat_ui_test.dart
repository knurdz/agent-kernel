import 'dart:io';

import 'package:agripilot_mobile/core/widgets/analysing_status.dart';
import 'package:agripilot_mobile/features/chat/data/chat_repository.dart';
import 'package:agripilot_mobile/features/chat/presentation/widgets/chat_bubble.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('parseChatResult', () {
    test('returns result string from map', () {
      expect(parseChatResult({'result': 'Hello farmer'}), 'Hello farmer');
    });

    test('returns fallback when result missing', () {
      expect(parseChatResult(<String, dynamic>{}), 'No reply received. Please try again.');
    });

    test('coerces non-string result', () {
      expect(parseChatResult({'result': 42}), '42');
    });
  });

  testWidgets('AnalysingStatus.photo shows first message', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: AnalysingStatus.photo()),
      ),
    );

    expect(find.text('Looking at your crop…'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('AnalysingStatus.text shows first message', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: AnalysingStatus.text()),
      ),
    );

    expect(find.text('Thinking about your question…'), findsOneWidget);
  });

  test('ChatBubble keeps image file for preview rendering', () {
    final image = File('crop.jpg');
    final bubble = ChatBubble(role: 'user', text: 'Leaf spots', image: image);

    expect(bubble.image, same(image));
    expect(bubble.text, 'Leaf spots');
  });

  testWidgets('ChatBubble renders caption text', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SizedBox(
            width: 320,
            child: ChatBubble(role: 'user', text: 'Leaf spots'),
          ),
        ),
      ),
    );

    expect(find.text('Leaf spots'), findsOneWidget);
  });
}
