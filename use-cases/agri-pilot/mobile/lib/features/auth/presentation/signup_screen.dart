import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/dio_client.dart';
import '../providers/auth_provider.dart';

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

  Future<void> _submit() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authControllerProvider.notifier).signup(
            role: _role,
            phone: _phone.text.trim(),
            password: _password.text,
            name: _name.text.trim(),
            district: _district.text.trim().isEmpty ? null : _district.text.trim(),
          );
    } catch (e) {
      setState(() => _error = e is ApiException ? e.message : e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Sign up')),
      body: ListView(
        padding: const EdgeInsets.all(24),
        children: [
          DropdownButtonFormField<String>(
            value: _role,
            items: const [
              DropdownMenuItem(value: 'farmer', child: Text('Farmer')),
              DropdownMenuItem(value: 'buyer', child: Text('Buyer')),
            ],
            onChanged: (v) => setState(() => _role = v ?? 'farmer'),
            decoration: const InputDecoration(labelText: 'Role'),
          ),
          TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name')),
          TextField(controller: _phone, decoration: const InputDecoration(labelText: 'Phone E.164')),
          TextField(controller: _district, decoration: const InputDecoration(labelText: 'District (optional)')),
          TextField(controller: _password, decoration: const InputDecoration(labelText: 'Password'), obscureText: true),
          if (_error != null) Text(_error!, style: const TextStyle(color: Colors.red)),
          const SizedBox(height: 16),
          FilledButton(onPressed: _loading ? null : _submit, child: Text(_loading ? '...' : 'Create account')),
          TextButton(onPressed: () => context.go('/login'), child: const Text('Back to login')),
        ],
      ),
    );
  }
}
