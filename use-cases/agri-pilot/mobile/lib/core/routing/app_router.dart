import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/signup_screen.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../features/channels/presentation/channels_screen.dart';
import '../../features/chat/presentation/chat_screen.dart';
import '../../features/connections/presentation/connections_screen.dart';
import '../../features/plants/presentation/plant_detail_screen.dart';
import '../../features/plants/presentation/plant_list_screen.dart';
import '../../features/plants/presentation/quick_scan_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';
import '../shell/home_screen.dart';
import '../shell/main_shell.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final refreshListenable = ValueNotifier<int>(0);

  ref.listen(authControllerProvider, (_, __) {
    refreshListenable.value++;
  });
  ref.onDispose(refreshListenable.dispose);

  return GoRouter(
    initialLocation: '/login',
    refreshListenable: refreshListenable,
    redirect: (context, state) {
      final auth = ref.read(authControllerProvider);
      final loggedIn = auth.asData?.value != null;
      final onAuth = state.matchedLocation == '/login' || state.matchedLocation == '/signup';
      if (!loggedIn && !onAuth) return '/login';
      if (loggedIn && onAuth) return '/home';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/signup', builder: (_, __) => const SignupScreen()),
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) {
          return MainShell(navigationShell: navigationShell);
        },
        branches: [
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/home',
                builder: (_, __) => const HomeScreen(),
                routes: [
                  GoRoute(
                    path: 'plants',
                    builder: (_, __) => const PlantListScreen(),
                    routes: [
                      GoRoute(
                        path: ':plantId',
                        builder: (_, state) => PlantDetailScreen(
                          plantId: int.parse(state.pathParameters['plantId']!),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/chat',
                builder: (_, state) => ChatScreen(initialPrompt: state.extra as String?),
                routes: [
                  GoRoute(
                    path: 'scan',
                    builder: (_, __) => const QuickScanScreen(),
                  ),
                ],
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/connections',
                builder: (_, __) => const ConnectionsScreen(),
              ),
            ],
          ),
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/profile',
                builder: (_, __) => const ProfileScreen(),
                routes: [
                  GoRoute(
                    path: 'channels',
                    builder: (_, __) => const ChannelsScreen(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
