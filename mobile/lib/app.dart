import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'screens/driver_home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';
import 'services/ble_service.dart';
import 'services/persistent_runtime_service.dart';
import 'utils/app_shutdown.dart';
import 'widgets/aervyx_logo.dart';

class AervyxApp extends StatefulWidget {
  const AervyxApp({super.key});

  @override
  State<AervyxApp> createState() => _AervyxAppState();
}

class _AervyxAppState extends State<AervyxApp> with WidgetsBindingObserver {
  bool _runtimeStartRequested = false;
  bool _runtimeBatteryShutdownStarted = false;
  Timer? _runtimeBatteryTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureRuntime());
    _runtimeBatteryTimer = Timer.periodic(
      const Duration(minutes: 1),
      (_) => _checkRuntimeBatteryThreshold(),
    );
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _checkRuntimeBatteryThreshold(),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _runtimeBatteryTimer?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _ensureRuntime();
      final auth = context.read<AuthService>();
      if (auth.isLoggedIn) {
        unawaited(context.read<BleService>().restoreAutoReconnect());
      }
    }
  }

  Future<void> _ensureRuntime() async {
    if (_runtimeStartRequested) return;
    _runtimeStartRequested = true;
    try {
      await PersistentRuntimeService.requestNotificationPermission()
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      // The runtime can still run as a foreground service if this request fails.
    }
    try {
      await PersistentRuntimeService.start()
          .timeout(const Duration(seconds: 5));
      if (mounted && context.read<AuthService>().isLoggedIn) {
        unawaited(context.read<BleService>().restoreAutoReconnect());
      }
    } catch (_) {
      // If Android blocks startup, opening the app again retries from a visible state.
    } finally {
      _runtimeStartRequested = false;
    }
  }

  Future<void> _checkRuntimeBatteryThreshold() async {
    if (_runtimeBatteryShutdownStarted) return;
    try {
      final threshold =
          await PersistentRuntimeService.getAutoExitBatteryThreshold();
      if (threshold == null) return;
      final level = await PersistentRuntimeService.getBatteryLevel();
      final charging = await PersistentRuntimeService.isBatteryCharging();
      if (level == null || charging == true || level > threshold || !mounted) {
        return;
      }

      _runtimeBatteryShutdownStarted = true;
      await shutDownApp(context);
    } catch (_) {
      // Battery data is best effort; the native service has its own guard too.
    }
  }

  @override
  Widget build(BuildContext context) {
    // Make the system status bar and nav bar black to match
    SystemChrome.setSystemUIOverlayStyle(const SystemUiOverlayStyle(
      statusBarColor: Colors.black,
      systemNavigationBarColor: Colors.black,
    ));

    return MaterialApp(
      title: 'Aervyx',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorSchemeSeed: const Color(0xFF00E5FF),
        useMaterial3: true,
        brightness: Brightness.light,
      ),
      darkTheme: ThemeData(
        colorSchemeSeed: const Color(0xFF00E5FF),
        useMaterial3: true,
        brightness: Brightness.dark,
      ),
      home: Consumer<AuthService>(
        builder: (context, auth, _) {
          if (auth.loading) {
            // Show the logo on black while restoring session — matches login screen
            return const Scaffold(
              backgroundColor: Colors.black,
              body: Center(child: AervyxLogo(size: 80)),
            );
          }
          if (!auth.isLoggedIn) return const LoginScreen();
          // Route by profile type — drivers get a dedicated screen
          if (auth.user?.profileType == 'driver') {
            return const DriverHomeScreen();
          }
          return const HomeScreen();
        },
      ),
    );
  }
}
