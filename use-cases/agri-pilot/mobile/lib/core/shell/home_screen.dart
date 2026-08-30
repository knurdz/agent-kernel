import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../features/auth/providers/auth_provider.dart';
import '../../features/marketplace/presentation/buyer_home_screen.dart';
import '../../features/marketplace/presentation/farmer_home_screen.dart';

/// Role-aware home tab content.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authControllerProvider).asData?.value;
    if (user == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    return user.isFarmer ? const FarmerHomeScreen() : const BuyerHomeScreen();
  }
}
