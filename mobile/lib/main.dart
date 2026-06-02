import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/background_service.dart';
import 'services/ble_service.dart';
import 'services/igc_service.dart';
import 'services/driver_service.dart';
import 'services/routing_service.dart';
import 'services/tracking_service.dart';
import 'services/update_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize background service (notification channel, service config)
  try {
    await BackgroundTrackingService.initialize();
  } catch (_) {
    // Background service init failed — app still works in foreground-only mode
  }

  final apiService = ApiService();
  final updateService = UpdateService(apiService);
  final authService = AuthService(apiService);
  final igcService = IgcService();
  late final TrackingService trackingService;
  final bleService = BleService(
    apiService,
    batteryThresholdProvider: () => trackingService.batteryThreshold,
  );
  trackingService = TrackingService(
    apiService,
    authService,
    igcService,
    meshReconnectRequester: ({bool force = false}) async {
      if (!bleService.isConnected) {
        await bleService.restoreAutoReconnect(force: force);
      }
    },
  );

  // Restore session with a safety net — app must never hang on startup
  try {
    await authService.tryRestoreSession();
  } catch (_) {
    // If anything goes wrong, proceed to login screen
  }

  if (authService.isLoggedIn) {
    try {
      await trackingService.restoreActiveSession();
    } catch (_) {
      // Tracking resume is best effort; the app should still open normally.
    }
  }

  // Sync platform config (MQTT + device profiles) in background after auth
  if (authService.isLoggedIn) {
    // Don't await — let it run in background so app opens immediately
    unawaited(bleService.syncPlatformConfig());
    unawaited(bleService.restoreAutoReconnect());
  }

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
        Provider<UpdateService>.value(value: updateService),
        ChangeNotifierProvider<AuthService>.value(value: authService),
        ChangeNotifierProvider<IgcService>.value(value: igcService),
        ChangeNotifierProvider<TrackingService>.value(value: trackingService),
        ChangeNotifierProvider<BleService>.value(value: bleService),
        ChangeNotifierProvider<DriverService>(
          create: (_) => DriverService(apiService),
        ),
        ChangeNotifierProvider<RoutingService>(
          create: (_) => RoutingService(apiService),
        ),
      ],
      child: const AervyxApp(),
    ),
  );
}
