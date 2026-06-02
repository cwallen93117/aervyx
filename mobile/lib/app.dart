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
import 'services/tracking_service.dart';
import 'services/update_service.dart';
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
  bool _updateCheckRequested = false;
  bool _updateDialogShowing = false;
  AuthService? _authService;
  Timer? _runtimeBatteryTimer;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => _ensureRuntime());
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkForAppUpdate());
    _runtimeBatteryTimer = Timer.periodic(
      const Duration(minutes: 1),
      (_) => _checkRuntimeBatteryThreshold(),
    );
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _checkRuntimeBatteryThreshold(),
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final auth = context.read<AuthService>();
    if (_authService == auth) return;
    _authService?.removeListener(_handleAuthChanged);
    _authService = auth;
    _authService?.addListener(_handleAuthChanged);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _authService?.removeListener(_handleAuthChanged);
    _runtimeBatteryTimer?.cancel();
    super.dispose();
  }

  void _handleAuthChanged() {
    if (!mounted) return;
    if (_authService?.isLoggedIn == true) {
      final ble = context.read<BleService>();
      unawaited(ble.syncPlatformConfig());
      unawaited(ble.restoreAutoReconnect());
    }
    if (_authService?.user?.profileType == 'driver') return;
    final tracking = context.read<TrackingService>();
    if (tracking.isDriverTracking) {
      unawaited(tracking.stopTracking());
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _ensureRuntime();
      final auth = context.read<AuthService>();
      if (auth.isLoggedIn) {
        unawaited(auth.refreshUserProfile().catchError((_) {}));
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

  Future<void> _checkForAppUpdate() async {
    if (_updateCheckRequested || _updateDialogShowing || !mounted) return;
    _updateCheckRequested = true;
    try {
      final release = await context.read<UpdateService>().checkForUpdate();
      if (release == null || !mounted) return;
      await _showUpdateDialog(release);
    } catch (_) {
      // Update checks should never block app startup.
    }
  }

  Future<void> _showUpdateDialog(AppReleaseInfo release) async {
    if (_updateDialogShowing) return;
    _updateDialogShowing = true;
    var downloading = false;
    var progress = 0.0;

    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: !downloading,
        builder: (dialogContext) {
          return StatefulBuilder(
            builder: (context, setDialogState) {
              Future<void> startUpdate() async {
                setDialogState(() {
                  downloading = true;
                  progress = 0;
                });
                try {
                  await context.read<UpdateService>().downloadAndInstall(
                    release,
                    onProgress: (value) {
                      if (!mounted) return;
                      setDialogState(() => progress = value.clamp(0, 1));
                    },
                  );
                  if (dialogContext.mounted) Navigator.of(dialogContext).pop();
                } on UpdateInstallPermissionException {
                  setDialogState(() => downloading = false);
                  await UpdateService.openInstallPermissionSettings();
                  if (!dialogContext.mounted) return;
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(
                      content: Text(
                        'Allow installs from Aervyx, then tap Update again.',
                      ),
                    ),
                  );
                } catch (_) {
                  setDialogState(() => downloading = false);
                  if (!dialogContext.mounted) return;
                  ScaffoldMessenger.of(dialogContext).showSnackBar(
                    const SnackBar(
                      content: Text('Update download failed. Try again.'),
                    ),
                  );
                }
              }

              return AlertDialog(
                title: const Text('Update available'),
                content: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Aervyx ${release.version}+${release.versionCode} is available.',
                    ),
                    if (release.releaseNotes.trim().isNotEmpty) ...[
                      const SizedBox(height: 12),
                      Text(
                        release.releaseNotes.trim(),
                        maxLines: 5,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                    if (downloading) ...[
                      const SizedBox(height: 16),
                      LinearProgressIndicator(value: progress),
                    ],
                  ],
                ),
                actions: [
                  TextButton(
                    onPressed:
                        downloading ? null : () => Navigator.of(context).pop(),
                    child: const Text('Later'),
                  ),
                  FilledButton.icon(
                    onPressed: downloading ? null : startUpdate,
                    icon: const Icon(Icons.system_update_alt),
                    label: Text(downloading ? 'Downloading' : 'Update'),
                  ),
                ],
              );
            },
          );
        },
      );
    } finally {
      _updateDialogShowing = false;
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
