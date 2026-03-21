import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/ble_service.dart';
import 'services/tracking_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final apiService = ApiService();
  final authService = AuthService(apiService);
  await authService.tryRestoreSession();

  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
        ChangeNotifierProvider<AuthService>.value(value: authService),
        ChangeNotifierProvider<TrackingService>(
          create: (_) => TrackingService(apiService),
        ),
        ChangeNotifierProvider<BleService>(
          create: (_) => BleService(apiService),
        ),
      ],
      child: const AervyxApp(),
    ),
  );
}
