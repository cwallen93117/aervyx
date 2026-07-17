import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'events_screen.dart';
import 'flights_screen.dart';
import 'home_screen.dart';
import 'live_view_screen.dart';
import 'settings_screen.dart';

enum MobileSwipePage { map, events, logbook, liveView, settings }

@visibleForTesting
List<MobileSwipePage> mobileSwipePages({required bool isDriver}) => [
      MobileSwipePage.map,
      MobileSwipePage.events,
      if (!isDriver) MobileSwipePage.logbook,
      MobileSwipePage.liveView,
      MobileSwipePage.settings,
    ];

class MobileSwipeShell extends StatelessWidget {
  const MobileSwipeShell({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final pages = mobileSwipePages(
      isDriver: auth.user?.profileType == 'driver',
    );
    final canManageEvents =
        auth.user?.role == 'admin' || auth.user?.role == 'organizer';

    return PageView(
      children: [
        for (final page in pages)
          switch (page) {
            MobileSwipePage.map => const HomeScreen(),
            MobileSwipePage.events => EventsScreen(
                api: context.read<ApiService>(),
                canManageEvents: canManageEvents,
              ),
            MobileSwipePage.logbook => const FlightsScreen(),
            MobileSwipePage.liveView => const LiveViewScreen(),
            MobileSwipePage.settings => const SettingsScreen(),
          },
      ],
    );
  }
}
