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

  // Restore session with a safety net — app must never hang on startup
  try {
    await authService.tryRestoreSession();
  } catch (_) {
    // If anything goes wrong, proceed to login screen
  }

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
        ChangeNotifierProvider<AuthService>.value(value: authService),
        ChangeNotifierProvider<IgcService>.value(value: igcService),
        ChangeNotifierProvider<TrackingService>(
          create: (_) => TrackingService(apiService, authService, igcService),
        ),
        ChangeNotifierProvider<BleService>(
          create: (_) => BleService(apiService),
        ),
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
