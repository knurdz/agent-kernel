import 'package:flutter/material.dart';

final _phoneRegex = RegExp(r'^\+[1-9]\d{7,14}$');
final _digitsOnly = RegExp(r'^\d+$');

/// Strips whitespace and common separators (legacy helper).
String normalizePhone(String phone) => phone.replaceAll(RegExp(r'[\s\-\(\)]'), '');

/// Normalizes Sri Lankan and E.164 phone input to +94XXXXXXXXX, or null if invalid.
String? normalizePhoneToE164(String input) {
  final stripped = normalizePhone(input.trim());
  if (stripped.isEmpty) return null;

  late final String candidate;
  if (stripped.startsWith('+')) {
    candidate = stripped;
  } else if (_digitsOnly.hasMatch(stripped)) {
    if (stripped.startsWith('94') && stripped.length == 11) {
      candidate = '+$stripped';
    } else if (stripped.startsWith('0') && stripped.length == 10) {
      candidate = '+94${stripped.substring(1)}';
    } else if (stripped.length == 9 && stripped.startsWith('7')) {
      candidate = '+94$stripped';
    } else {
      return null;
    }
  } else {
    return null;
  }

  return _phoneRegex.hasMatch(candidate) ? candidate : null;
}

String? validatePhone(String phone) {
  if (phone.trim().isEmpty) return 'Phone number is required.';
  if (normalizePhoneToE164(phone) == null) {
    return 'Enter a valid phone number.';
  }
  return null;
}

String? phoneForApi(String phone) => normalizePhoneToE164(phone);

String? validatePassword(String password, {required bool signup}) {
  if (password.isEmpty) return 'Password is required.';
  if (signup && password.length < 8) return 'Password must be at least 8 characters.';
  return null;
}

String? validateName(String name) {
  if (name.trim().isEmpty) return 'Name is required.';
  return null;
}

Widget authErrorBanner(String message) {
  return Container(
    width: double.infinity,
    padding: const EdgeInsets.all(12),
    margin: const EdgeInsets.only(top: 8, bottom: 8),
    decoration: BoxDecoration(
      color: Colors.red.shade50,
      border: Border.all(color: Colors.red.shade300),
      borderRadius: BorderRadius.circular(8),
    ),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(Icons.error_outline, color: Colors.red.shade700, size: 20),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            message,
            style: TextStyle(color: Colors.red.shade900),
          ),
        ),
      ],
    ),
  );
}
