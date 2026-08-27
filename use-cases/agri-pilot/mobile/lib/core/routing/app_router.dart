import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/login_screen.dart';
import '../../features/auth/presentation/signup_screen.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../features/channels/presentation/channels_screen.dart';
import '../../features/chat/presentation/chat_screen.dart';
import '../../features/connections/presentation/connections_screen.dart';
import '../../features/marketplace/presentation/buyer_home_screen.dart';
import '../../features/marketplace/presentation/farmer_home_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  final auth = ref.watch(authControllerProvider);
  return GoRouter(
    initialLocation: '/login',
    redirect: (context, state) {
      final loggedIn = auth.asData?.value != null;
      final onAuth = state.matchedLocation == '/login' || state.matchedLocation == '/signup';
      if (!loggedIn && !onAuth) return '/login';
      if (loggedIn && onAuth) {
        final user = auth.asData!.value!;
        return user.isFarmer ? '/farmer' : '/buyer';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, __) => const LoginScreen()),
      GoRoute(path: '/signup', builder: (_, __) => const SignupScreen()),
      GoRoute(path: '/farmer', builder: (_, __) => const FarmerHomeScreen()),
      GoRoute(path: '/buyer', builder: (_, __) => const BuyerHomeScreen()),
      GoRoute(path: '/chat', builder: (_, __) => const ChatScreen()),
      GoRoute(path: '/connections', builder: (_, __) => const ConnectionsScreen()),
      GoRoute(path: '/profile', builder: (_, __) => const ProfileScreen()),
      GoRoute(path: '/channels', builder: (_, __) => const ChannelsScreen()),
    ],
  );
});
