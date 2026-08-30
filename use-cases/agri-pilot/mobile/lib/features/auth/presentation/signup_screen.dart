import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../providers/auth_provider.dart';
import 'auth_form_helpers.dart';
import 'auth_screen_shell.dart';
import 'auth_text_field.dart';
import 'role_selector.dart';

class SignupScreen extends ConsumerStatefulWidget {
  const SignupScreen({super.key});

  @override
  ConsumerState<SignupScreen> createState() => _SignupScreenState();
}

class _SignupScreenState extends ConsumerState<SignupScreen> {
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  final _district = TextEditingController();
  String _role = 'farmer';
  var _loading = false;
  String? _error;

  @override
  void dispose() {
    _phone.dispose();
    _password.dispose();
    _name.dispose();
    _district.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final phoneInput = _phone.text.trim();
    final password = _password.text;
    final name = _name.text.trim();

    final nameError = validateName(name);
    if (nameError != null) {
      setState(() => _error = nameError);
      return;
    }
    final phoneError = validatePhone(phoneInput);
    if (phoneError != null) {
      setState(() => _error = phoneError);
      return;
    }
    final passwordError = validatePassword(password, signup: true);
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
      await ref.read(authControllerProvider.notifier).signup(
            role: _role,
            phone: phone,
            password: password,
            name: name,
            district: _district.text.trim().isEmpty ? null : _district.text.trim(),
          );
    } catch (e) {
      if (mounted) setState(() => _error = apiErrorMessage(e));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AuthScreenShell(
      subtitle: 'Create your account',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          RoleSelector(
            value: _role,
            onChanged: (v) => setState(() => _role = v),
          ),
          AuthTextField(
            controller: _name,
            label: 'Full name',
            prefixIcon: Icons.person_outline,
            textInputAction: TextInputAction.next,
          ),
          AuthTextField.phone(
            controller: _phone,
            textInputAction: TextInputAction.next,
          ),
          AuthTextField(
            controller: _district,
            label: 'District (optional)',
            prefixIcon: Icons.location_on_outlined,
            textInputAction: TextInputAction.next,
          ),
          AuthTextField.password(
            controller: _password,
            label: 'Password',
            helperText: 'At least 8 characters',
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
                : const Text('Create account'),
          ),
          const SizedBox(height: 8),
          TextButton(
            onPressed: _loading ? null : () => context.go('/login'),
            child: const Text('Already have an account? Log in'),
          ),
        ],
      ),
    );
  }
}
