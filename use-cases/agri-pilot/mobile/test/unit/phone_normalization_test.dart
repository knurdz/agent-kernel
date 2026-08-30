import 'package:flutter_test/flutter_test.dart';

import 'package:agripilot_mobile/features/auth/presentation/auth_form_helpers.dart';

void main() {
  group('normalizePhoneToE164', () {
    test('accepts local 0-prefix format', () {
      expect(normalizePhoneToE164('0741174199'), '+94741174199');
    });

    test('accepts 9-digit mobile without leading 0', () {
      expect(normalizePhoneToE164('741174199'), '+94741174199');
    });

    test('accepts country code without plus', () {
      expect(normalizePhoneToE164('94741175199'), '+94741175199');
    });

    test('accepts E.164 with spaces and dashes', () {
      expect(normalizePhoneToE164('+94 741-174 199'), '+94741174199');
    });

    test('accepts full E.164', () {
      expect(normalizePhoneToE164('+94771234567'), '+94771234567');
    });

    test('rejects too-short numbers', () {
      expect(normalizePhoneToE164('74115199'), isNull);
    });

    test('rejects empty input', () {
      expect(normalizePhoneToE164(''), isNull);
      expect(normalizePhoneToE164('   '), isNull);
    });

    test('rejects invalid characters', () {
      expect(normalizePhoneToE164('07abc74199'), isNull);
    });
  });

  group('validatePhone', () {
    test('returns null for valid Sri Lankan input', () {
      expect(validatePhone('0741174199'), isNull);
    });

    test('returns helpful error for invalid input', () {
      expect(
        validatePhone('74115199'),
        'Enter a valid number, e.g. 077 123 4567 or +94771234567.',
      );
    });

    test('returns required error for empty input', () {
      expect(validatePhone(''), 'Phone number is required.');
    });
  });

  group('phoneForApi', () {
    test('returns normalized E.164 for API calls', () {
      expect(phoneForApi('0741174199'), '+94741174199');
    });
  });
}
