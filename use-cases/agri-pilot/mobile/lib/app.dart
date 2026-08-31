import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/notifications/push_service.dart';
import 'core/routing/app_router.dart';
import 'core/theme/app_theme.dart';

class AgriPilotApp extends ConsumerStatefulWidget {
  const AgriPilotApp({super.key});

  @override
  ConsumerState<AgriPilotApp> createState() => _AgriPilotAppState();
}

class _AgriPilotAppState extends ConsumerState<AgriPilotApp> {
  @override
  void initState() {
    super.initState();
    PushService.registerOrderDeepLinkHandler((orderId) {
      ref.read(appRouterProvider).go('/orders/$orderId/track');
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      ref.read(pushServiceProvider).listenForNavigation();
    });
  }

  @override
  Widget build(BuildContext context) {
    final router = ref.watch(appRouterProvider);
    return MaterialApp.router(
      title: 'AgriPilot',
      theme: AppTheme.light,
      routerConfig: router,
    );
  }
}
