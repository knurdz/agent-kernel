import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/domain/models.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/signup_screen.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../features/channels/presentation/channels_screen.dart';
import '../../features/chat/presentation/advisor_threads_screen.dart';
import '../../features/chat/presentation/chat_screen.dart';
import '../../features/connections/presentation/connections_screen.dart';
import '../../features/delivery/presentation/order_tracking_screen.dart';
import '../../features/delivery/presentation/orders_list_screens.dart';
import '../../features/plants/presentation/plant_detail_screen.dart';
import '../../features/plants/presentation/plant_list_screen.dart';
import '../../features/plants/presentation/quick_scan_screen.dart';
import '../../features/marketplace/presentation/listing_detail_screen.dart';
import '../../features/marketplace/presentation/listing_insights_screen.dart';
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
      GoRoute(path: '/orders', builder: (_, __) => const BuyerOrdersScreen()),
      GoRoute(path: '/farmer-orders', builder: (_, __) => const FarmerOrdersScreen()),
      GoRoute(
        path: '/orders/:orderId/track',
        builder: (_, state) => OrderTrackingScreen(orderId: int.parse(state.pathParameters['orderId']!)),
      ),
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
                  GoRoute(
                    path: 'listings/:listingId',
                    builder: (_, state) => ListingDetailScreen(
                      listingId: int.parse(state.pathParameters['listingId']!),
                    ),
                    routes: [
                      GoRoute(
                        path: 'insights',
                        builder: (_, state) => ListingInsightsScreen(
                          listingId: int.parse(state.pathParameters['listingId']!),
                          listing: state.extra as Listing?,
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
                builder: (_, __) => const AdvisorThreadsScreen(),
                routes: [
                  GoRoute(
                    path: 't/:sessionId',
                    builder: (_, state) => ChatScreen(
                      sessionId: Uri.decodeComponent(state.pathParameters['sessionId']!),
                      initialPrompt: state.extra as String?,
                      threadName: state.uri.queryParameters['name'],
                    ),
                  ),
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
