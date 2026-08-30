import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/widgets/status_chip.dart';
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
  var _initialized = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final user = ref.read(authControllerProvider).asData?.value;
      if (user != null && mounted) {
        _name.text = user.name;
        _district.text = user.profile?.district ?? '';
        setState(() => _initialized = true);
      }
    });
  }

  @override
  void dispose() {
    _name.dispose();
    _district.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await ref.read(authRepositoryProvider).updateProfile({
      'name': _name.text.trim(),
      'district': _district.text.trim(),
    });
    await ref.read(authControllerProvider.notifier).refresh();
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Profile updated')),
      );
    }
  }

  String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return '${parts.first[0]}${parts.last[0]}'.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authControllerProvider).asData?.value;
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Me'),
      ),
      body: user == null
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Center(
                  child: CircleAvatar(
                    radius: 40,
                    backgroundColor: theme.colorScheme.primaryContainer,
                    child: Text(
                      _initials(user.name),
                      style: theme.textTheme.headlineSmall?.copyWith(
                        color: theme.colorScheme.onPrimaryContainer,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Center(
                  child: Text(
                    user.name,
                    style: theme.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: 4),
                Center(
                  child: Text(
                    user.phoneNumber,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: [
                    Chip(
                      avatar: Icon(
                        user.isFarmer
                            ? Icons.grass
                            : user.isRider
                                ? Icons.local_shipping_outlined
                                : Icons.storefront_outlined,
                        size: 18,
                        color: theme.colorScheme.primary,
                      ),
                      label: Text(
                        user.isFarmer
                            ? 'Farmer'
                            : user.isRider
                                ? 'Rider'
                                : 'Buyer',
                      ),
                    ),
                    if (user.isFarmer)
                      StatusChip(status: user.subscriptionStatus == 'active' ? 'active' : 'expired'),
                  ],
                ),
                const SizedBox(height: 24),
                Card(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Text(
                          'Profile details',
                          style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 16),
                        TextField(
                          controller: _name,
                          decoration: const InputDecoration(
                            labelText: 'Name',
                            prefixIcon: Icon(Icons.person_outline),
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _district,
                          decoration: const InputDecoration(
                            labelText: 'District',
                            prefixIcon: Icon(Icons.location_on_outlined),
                          ),
                        ),
                        const SizedBox(height: 16),
                        FilledButton(onPressed: _save, child: const Text('Save changes')),
                      ],
                    ),
                  ),
                ),
                if (user.isFarmer) ...[
                  const SizedBox(height: 12),
                  Card(
                    child: ListTile(
                      leading: Icon(Icons.link, color: theme.colorScheme.primary),
                      title: const Text('Channels'),
                      subtitle: const Text('WhatsApp & Telegram'),
                      trailing: const Icon(Icons.chevron_right),
                      onTap: () => context.push('/profile/channels'),
                    ),
                  ),
                ],
                const SizedBox(height: 24),
                OutlinedButton.icon(
                  onPressed: () async {
                    await ref.read(authControllerProvider.notifier).logout();
                    if (context.mounted) context.go('/login');
                  },
                  icon: Icon(Icons.logout, color: theme.colorScheme.error),
                  label: Text(
                    'Log out',
                    style: TextStyle(color: theme.colorScheme.error),
                  ),
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: theme.colorScheme.error.withValues(alpha: 0.5)),
                  ),
                ),
              ],
            ),
    );
  }
}
