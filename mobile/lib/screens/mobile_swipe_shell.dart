import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'challenges_screen.dart';
import 'flights_screen.dart';
import 'home_screen.dart';
import 'settings_screen.dart';

enum MobileSwipePage { map, logbook, challenges, settings }

@visibleForTesting
List<MobileSwipePage> mobileSwipePages({required bool isDriver}) => [
      MobileSwipePage.map,
      if (!isDriver) MobileSwipePage.logbook,
      MobileSwipePage.challenges,
      MobileSwipePage.settings,
    ];

class MobileSwipeShell extends StatelessWidget {
  const MobileSwipeShell({super.key});

  @override
  Widget build(BuildContext context) {
    final pages = mobileSwipePages(
      isDriver: context.watch<AuthService>().user?.profileType == 'driver',
    );

    return PageView(
      children: [
        for (final page in pages)
          switch (page) {
            MobileSwipePage.map => const HomeScreen(),
            MobileSwipePage.logbook => const FlightsScreen(),
            MobileSwipePage.challenges => ChallengesScreen(
                api: context.read<ApiService>(),
              ),
            MobileSwipePage.settings => const SettingsScreen(),
          },
      ],
    );
  }
}
