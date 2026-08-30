import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../providers/auth_provider.dart';
import 'auth_form_helpers.dart';
import 'auth_screen_shell.dart';
import 'auth_text_field.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  var _loading = false;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final phoneInput = _phone.text.trim();
    final password = _password.text;

    final phoneError = validatePhone(phoneInput);
    if (phoneError != null) {
      setState(() => _error = phoneError);
      return;
    }
    final passwordError = validatePassword(password, signup: false);
    if (passwordError != null) {
      setState(() => _error = passwordError);
      return;
    }

    final phone = phoneForApi(phoneInput)!;

    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider.notifier).login(phone, password);
    } catch (e) {
      if (mounted) setState(() => _error = apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenShell(
      subtitle: 'Welcome back',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AuthTextField.phone(
            controller: _phone,
            textInputAction: TextInputAction.next,
          ),
          AuthTextField.password(
            controller: _password,
            label: 'Password',
            textInputAction: TextInputAction.done,
            onSubmitted: (_) => _loading ? null : _submit(),
          ),
          if (_error != null) authErrorBanner(_error!),
          const SizedBox(height: 8),
          FilledButton(
            onPressed: _loading ? null : _submit,
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
            child: _loading
                ? const SizedBox(
                    height: 22,
                    width: 22,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Log in'),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _loading ? null : () => context.go('/signup'),
            child: const Text('Create account'),
          ),
        ],
      ),
    );
  }
}
