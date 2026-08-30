import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/providers/auth_provider.dart';
import '../../features/marketplace/data/marketplace_repository.dart';

/// Pending inbox count for NavigationBar badge.
final pendingConnectionsCountProvider = FutureProvider<int>((ref) async {
  final user = ref.watch(authControllerProvider).asData?.value;
  if (user == null) return 0;

  final repo = ref.watch(marketplaceRepositoryProvider);
  final items = user.isFarmer ? await repo.farmerConnections() : await repo.buyerConnections();
  return items.where((c) => c.status == 'pending').length;
});

class MainShell extends ConsumerWidget {
  const MainShell({super.key, required this.navigationShell});

  final StatefulNavigationShell navigationShell;

  void _onTap(int index) {
    navigationShell.goBranch(
      index,
      initialLocation: index == navigationShell.currentIndex,
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).asData?.value;
    final isRider = user?.isRider == true;
    final isBuyer = user?.isBuyer == true;
    final isFarmer = user?.isFarmer == true;
    final pendingAsync = ref.watch(pendingConnectionsCountProvider);
    final pendingCount = pendingAsync.asData?.value ?? 0;
    final inboxLabel = isRider ? 'Deliveries' : (isBuyer ? 'Orders' : 'Inbox');

    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: navigationShell.currentIndex,
        onDestinationSelected: _onTap,
        destinations: [
          NavigationDestination(
            icon: Icon(isRider ? Icons.work_outline : Icons.home_outlined),
            selectedIcon: Icon(isRider ? Icons.work : Icons.home),
            label: isRider ? 'Jobs' : 'Home',
          ),
          const NavigationDestination(
            icon: Icon(Icons.smart_toy_outlined),
            selectedIcon: Icon(Icons.smart_toy),
            label: 'Advisor',
          ),
          NavigationDestination(
            icon: pendingCount > 0 && isFarmer
                ? Badge(label: Text('$pendingCount'), child: const Icon(Icons.inbox_outlined))
                : Icon(isRider ? Icons.local_shipping_outlined : Icons.receipt_long_outlined),
            selectedIcon: pendingCount > 0 && isFarmer
                ? Badge(label: Text('$pendingCount'), child: const Icon(Icons.inbox))
                : Icon(isRider ? Icons.local_shipping : Icons.receipt_long),
            label: inboxLabel,
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Me',
          ),
        ],
      ),
    );
  }
}
