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

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize background service (notification channel, service config)
  try {
    await BackgroundTrackingService.initialize();
  } catch (_) {
    // Background service init failed — app still works in foreground-only mode
  }

  final apiService = ApiService();
  final authService = AuthService(apiService);
  final igcService = IgcService();
  final trackingService = TrackingService(apiService, authService, igcService);

  // Restore session with a safety net — app must never hang on startup
  try {
    await authService.tryRestoreSession();
  } catch (_) {
    // If anything goes wrong, proceed to login screen
  }

  // Sync platform config (MQTT + device profiles) in background after auth
  final bleService = BleService(
    apiService,
    batteryThresholdProvider: () => trackingService.batteryThreshold,
  );
  if (authService.isLoggedIn) {
    // Don't await — let it run in background so app opens immediately
    unawaited(bleService.syncPlatformConfig());
    unawaited(bleService.restoreAutoReconnect());
  }

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
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
