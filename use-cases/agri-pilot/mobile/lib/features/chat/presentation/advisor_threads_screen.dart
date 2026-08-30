import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/start_tracking_crop_banner.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../plants/data/plants_repository.dart';
import '../data/chat_repository.dart';

class AdvisorThreadsScreen extends ConsumerStatefulWidget {
  const AdvisorThreadsScreen({super.key});

  @override
  ConsumerState<AdvisorThreadsScreen> createState() => _AdvisorThreadsScreenState();
}

class _AdvisorThreadsScreenState extends ConsumerState<AdvisorThreadsScreen> {
  List<ThreadSummary> _threads = [];
  var _loading = true;
  var _showTrackingBanner = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final repo = ref.read(chatRepositoryProvider);
      final plantsRepo = ref.read(plantsRepositoryProvider);
      final results = await Future.wait([
        repo.listThreads(),
        plantsRepo.listPlants().catchError((_) => <PlantSummary>[]),
      ]);
      if (!mounted) return;
      setState(() {
        _threads = results[0] as List<ThreadSummary>;
        _showTrackingBanner = (results[1] as List<PlantSummary>).isEmpty;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = apiErrorMessage(e);
        _loading = false;
      });
    }
  }

  void _openNewThread() {
    final user = ref.read(authControllerProvider).value;
    if (user == null) return;
    final sessionId = newThreadSessionId(user.id);
    context.push('/chat/t/${Uri.encodeComponent(sessionId)}').then((_) {
      if (mounted) _refresh();
    });
  }

  void _openThread(ThreadSummary thread) {
    final name = Uri.encodeQueryComponent(thread.name);
    context.push('/chat/t/${Uri.encodeComponent(thread.sessionId)}?name=$name').then((_) {
      if (mounted) _refresh();
    });
  }

  String _formatUpdatedAt(DateTime updatedAt) {
    final now = DateTime.now();
    final local = updatedAt.toLocal();
    if (now.difference(local).inDays == 0) {
      return DateFormat.jm().format(local);
    }
    if (now.difference(local).inDays < 7) {
      return DateFormat.E().add_jm().format(local);
    }
    return DateFormat.yMMMd().format(local);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: const Text('AgriPilot Advisor'),
        actions: [
          IconButton(
            tooltip: 'New conversation',
            onPressed: _openNewThread,
            icon: const Icon(Icons.add_comment_outlined),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _loading
            ? ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 120),
                  Center(child: CircularProgressIndicator()),
                ],
              )
            : _error != null
                ? ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(16),
                    children: [
                      if (_showTrackingBanner) const StartTrackingCropBanner(),
                      Card(
                        color: theme.colorScheme.errorContainer,
                        child: Padding(
                          padding: const EdgeInsets.all(16),
                          child: Text(
                            _error!,
                            style: TextStyle(color: theme.colorScheme.onErrorContainer),
                          ),
                        ),
                      ),
                    ],
                  )
                : _threads.isEmpty
                    ? ListView(
                        physics: const AlwaysScrollableScrollPhysics(),
                        children: [
                          if (_showTrackingBanner) const StartTrackingCropBanner(),
                          EmptyState(
                            icon: Icons.forum_outlined,
                            title: 'No conversations yet',
                            subtitle: 'Start a new chat about crops, diseases, weather, or send a photo for diagnosis.',
                            actionLabel: 'New conversation',
                            onAction: _openNewThread,
                          ),
                        ],
                      )
                    : ListView.separated(
                        physics: const AlwaysScrollableScrollPhysics(),
                        itemCount: _threads.length + (_showTrackingBanner ? 1 : 0),
                        separatorBuilder: (_, __) => const Divider(height: 1, indent: 72),
                        itemBuilder: (context, index) {
                          if (_showTrackingBanner && index == 0) {
                            return const StartTrackingCropBanner();
                          }
                          final thread = _threads[index - (_showTrackingBanner ? 1 : 0)];
                          return ListTile(
                            leading: CircleAvatar(
                              backgroundColor: theme.colorScheme.primaryContainer,
                              child: Icon(Icons.chat_bubble_outline, color: theme.colorScheme.onPrimaryContainer),
                            ),
                            title: Text(thread.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                            subtitle: Text('Updated ${_formatUpdatedAt(thread.updatedAt)}'),
                            trailing: const Icon(Icons.chevron_right),
                            onTap: () => _openThread(thread),
                          );
                        },
                      ),
      ),
      floatingActionButton: _threads.isNotEmpty
          ? FloatingActionButton.extended(
              onPressed: _openNewThread,
              icon: const Icon(Icons.add),
              label: const Text('New chat'),
            )
          : null,
    );
  }
}
