import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/network/dio_client.dart';
import '../../../core/widgets/empty_state.dart';
import '../../auth/domain/models.dart';
import '../../auth/providers/auth_provider.dart';
import '../../plants/data/plants_repository.dart';
import '../../plants/presentation/widgets/my_plants_banner.dart';
import '../data/chat_repository.dart';
import '../domain/thread_title.dart';

class AdvisorThreadsScreen extends ConsumerStatefulWidget {
  const AdvisorThreadsScreen({super.key});

  @override
  ConsumerState<AdvisorThreadsScreen> createState() => _AdvisorThreadsScreenState();
}

class _AdvisorThreadsScreenState extends ConsumerState<AdvisorThreadsScreen> {
  List<ThreadSummary> _threads = [];
  List<PlantSummary> _plants = [];
  var _loading = true;
  String? _error;

  bool get _isFarmer => ref.read(authControllerProvider).asData?.value?.isFarmer == true;

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
      final futures = <Future<dynamic>>[repo.listThreads()];
      if (_isFarmer) {
        futures.add(plantsRepo.listPlants().catchError((_) => <PlantSummary>[]));
      }
      final results = await Future.wait(futures);
      if (!mounted) return;
      setState(() {
        _threads = results[0] as List<ThreadSummary>;
        _plants = _isFarmer && results.length > 1 ? results[1] as List<PlantSummary> : [];
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

  String _displayName(ThreadSummary thread) {
    if (!isGenericThreadTitle(thread.name)) return thread.name;
    return deriveThreadTitle(prompt: thread.name, at: thread.updatedAt);
  }

  void _openThread(ThreadSummary thread) {
    final name = Uri.encodeQueryComponent(_displayName(thread));
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
    final isFarmer = ref.watch(authControllerProvider).asData?.value?.isFarmer == true;
    final isBuyer = ref.watch(authControllerProvider).asData?.value?.isBuyer == true;
    final isRider = ref.watch(authControllerProvider).asData?.value?.isRider == true;

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
            : CustomScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                slivers: [
                  if (isFarmer) SliverToBoxAdapter(child: MyPlantsBanner(plants: _plants)),
                  if (_error != null)
                    SliverToBoxAdapter(
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Card(
                          color: theme.colorScheme.errorContainer,
                          child: Padding(
                            padding: const EdgeInsets.all(16),
                            child: Text(
                              _error!,
                              style: TextStyle(color: theme.colorScheme.onErrorContainer),
                            ),
                          ),
                        ),
                      ),
                    )
                  else if (_threads.isEmpty)
                    SliverFillRemaining(
                      hasScrollBody: false,
                      child: EmptyState(
                        icon: Icons.forum_outlined,
                        title: 'No conversations yet',
                        subtitle: isRider
                            ? 'Ask about nearby jobs, active deliveries, going online, or buyer PIN at drop-off.'
                            : isBuyer
                                ? 'Ask about finding crops, farm health on listings, orders, or delivery.'
                                : 'Start a new chat about crops, diseases, weather, or send a photo for diagnosis.',
                        actionLabel: 'New conversation',
                        onAction: _openNewThread,
                      ),
                    )
                  else
                    SliverList.separated(
                      itemCount: _threads.length,
                      separatorBuilder: (_, _) => const Divider(height: 1, indent: 72),
                      itemBuilder: (context, index) {
                        final thread = _threads[index];
                        return ListTile(
                          leading: CircleAvatar(
                            backgroundColor: theme.colorScheme.primaryContainer,
                            child: Icon(Icons.chat_bubble_outline, color: theme.colorScheme.onPrimaryContainer),
                          ),
                          title: Text(_displayName(thread), maxLines: 1, overflow: TextOverflow.ellipsis),
                          subtitle: Text('Updated ${_formatUpdatedAt(thread.updatedAt)}'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () => _openThread(thread),
                        );
                      },
                    ),
                ],
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
