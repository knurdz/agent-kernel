import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../auth/data/auth_repository.dart';
import '../../auth/providers/auth_provider.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  final _name = TextEditingController();
  final _district = TextEditingController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = ref.read(authControllerProvider).asData?.value;
      _name.text = user?.name ?? '';
      _district.text = user?.profile?.district ?? '';
    });
  }

  Future<void> _save() async {
    await ref.read(authRepositoryProvider).updateProfile({
      'name': _name.text.trim(),
      'district': _district.text.trim(),
    });
    await ref.read(authControllerProvider.notifier).refresh();
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Profile updated')));
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).asData?.value;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile'), leading: BackButton(onPressed: () => context.pop())),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Text('${user?.role ?? ''} · ${user?.phoneNumber ?? ''}'),
            Text('Subscription: ${user?.subscriptionStatus ?? ''}'),
            TextField(controller: _name, decoration: const InputDecoration(labelText: 'Name')),
            TextField(controller: _district, decoration: const InputDecoration(labelText: 'District')),
            const SizedBox(height: 12),
            FilledButton(onPressed: _save, child: const Text('Save')),
            const Spacer(),
            OutlinedButton(
              onPressed: () async {
                await ref.read(authControllerProvider.notifier).logout();
                if (context.mounted) context.go('/login');
              },
              child: const Text('Logout'),
            ),
          ],
        ),
      ),
    );
  }
}
