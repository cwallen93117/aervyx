import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/ble_service.dart';
import 'services/igc_service.dart';
import 'services/tracking_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

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
          create: (_) => TrackingService(apiService, igcService),
        ),
        ChangeNotifierProvider<BleService>(
          create: (_) => BleService(apiService),
        ),
      ],
      child: const AervyxApp(),
    ),
  );
}
