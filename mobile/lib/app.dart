import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'screens/driver_home_screen.dart';
import 'screens/login_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';
import 'services/persistent_runtime_service.dart';
import 'widgets/aervyx_logo.dart';

class AervyxApp extends StatefulWidget {
  const AervyxApp({super.key});

  @override
  State<AervyxApp> createState() => _AervyxAppState();
}

class _AervyxAppState extends State<AervyxApp> with WidgetsBindingObserver {
  bool _runtimeStartRequested = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureRuntime());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _ensureRuntime();
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
    } catch (_) {
      // If Android blocks startup, opening the app again retries from a visible state.
    } finally {
      _runtimeStartRequested = false;
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
