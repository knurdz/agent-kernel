import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../auth/domain/models.dart';
import '../../auth/data/auth_repository.dart';
import '../../marketplace/data/marketplace_repository.dart';

class ChannelsScreen extends ConsumerStatefulWidget {
  const ChannelsScreen({super.key});

  @override
  ConsumerState<ChannelsScreen> createState() => _ChannelsScreenState();
}

class _ChannelsScreenState extends ConsumerState<ChannelsScreen> {
  ChannelsStatus? _status;
  PublicConfig? _config;
  var _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      _status = await ref.read(authRepositoryProvider).channels();
      _config = await ref.read(marketplaceRepositoryProvider).publicConfig();
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openUrl(String? url) async {
    if (url == null) return;
    final uri = Uri.parse(url);
    if (await canLaunchUrl(uri)) await launchUrl(uri, mode: LaunchMode.externalApplication);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Channels'), leading: BackButton(onPressed: () => context.pop())),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                ListTile(
                  title: const Text('WhatsApp'),
                  subtitle: Text(_status?.whatsappEligible == true
                      ? 'Message from your registered phone to reach the bot'
                      : 'Active farmer subscription required'),
                  trailing: IconButton(
                    icon: const Icon(Icons.open_in_new),
                    onPressed: () => _openUrl(_config?.whatsappWaMe),
                  ),
                ),
                ListTile(
                  title: const Text('Telegram'),
                  subtitle: Text(_status?.telegramLinked == true ? 'Linked' : 'Not linked'),
                  trailing: _status?.telegramLinked == true
                      ? IconButton(
                          icon: const Icon(Icons.link_off),
                          onPressed: () async {
                            await ref.read(authRepositoryProvider).unlinkTelegram();
                            await _load();
                          },
                        )
                      : FilledButton(
                          onPressed: () async {
                            final url = await ref.read(authRepositoryProvider).telegramLinkUrl();
                            await _openUrl(url);
                          },
                          child: const Text('Link'),
                        ),
                ),
                if (_status?.telegramLinked != true)
                  const Padding(
                    padding: EdgeInsets.all(8),
                    child: Text(
                      'Fallback: open the bot in Telegram and share your phone contact if the link expires.',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ),
              ],
            ),
    );
  }
}
