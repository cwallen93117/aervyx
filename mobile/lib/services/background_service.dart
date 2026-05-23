import 'dart:async';
import 'dart:ui';

import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:geolocator/geolocator.dart';

/// Manages the Android foreground service for continuous GPS tracking
/// when the app is backgrounded or the screen is off.
///
/// Architecture:
/// - The background isolate runs GPS and sends position data via `invoke()`.
/// - The foreground UI (TrackingService) listens via `on()` and updates state.
/// - A persistent notification shows tracking status.
class BackgroundTrackingService {
  static const String _notificationChannelId = 'aervyx_tracking';
  static const String _notificationChannelName = 'Flight Tracking';
  static const int _notificationId = 888;

  static final FlutterBackgroundService _service = FlutterBackgroundService();

  /// Initialize the background service. Call once from main().
  static Future<void> initialize() async {
    // Set up notification channel for the foreground service
    final flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();

    const androidChannel = AndroidNotificationChannel(
      _notificationChannelId,
      _notificationChannelName,
      description: 'Shows flight tracking status',
      importance: Importance.low, // Low = no sound, stays in tray
    );

    await flutterLocalNotificationsPlugin
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(androidChannel);

    await _service.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: _onStart,
        autoStart: false,
        autoStartOnBoot: false,
        isForegroundMode: true,
        foregroundServiceNotificationId: _notificationId,
        initialNotificationTitle: 'Aervyx',
        initialNotificationContent: 'Ready to track',
        notificationChannelId: _notificationChannelId,
        foregroundServiceTypes: [AndroidForegroundType.location],
      ),
      // iOS configuration (minimal — GPS background mode handled by iOS natively)
      iosConfiguration: IosConfiguration(
        autoStart: false,
        onForeground: _onStart,
        onBackground: _onIosBackground,
      ),
    );
  }

  /// Start the foreground service.
  static Future<void> start() async {
    final isRunning = await _service.isRunning();
    if (!isRunning) {
      await _service.startService();
    }
    _service.invoke('startTracking');
  }

  /// Stop the foreground service.
  static Future<void> stop() async {
    _service.invoke('stopTracking');
    // Give it a moment to clean up, then stop the service
    await Future.delayed(const Duration(milliseconds: 500));
    final isRunning = await _service.isRunning();
    if (isRunning) {
      _service.invoke('stopService');
    }
  }

  /// Update the notification content (called from TrackingService).
  static void updateNotification({
    required String title,
    required String content,
  }) {
    _service.invoke('updateNotification', {
      'title': title,
      'content': content,
    });
  }

  /// Listen for position updates from the background service.
  static Stream<Map<String, dynamic>?> get onPositionUpdate {
    return _service.on('positionUpdate');
  }

  /// Listen for status messages from the background service.
  static Stream<Map<String, dynamic>?> get onStatusUpdate {
    return _service.on('statusUpdate');
  }

  /// Check if the background service is currently running.
  static Future<bool> get isRunning => _service.isRunning();
}

// ═══════════════════════════════════════════════════════════════════════════
// Background Isolate Entry Points
// ═══════════════════════════════════════════════════════════════════════════

/// Entry point for the background isolate (Android).
@pragma('vm:entry-point')
Future<void> _onStart(ServiceInstance service) async {
  // Ensure Flutter bindings are initialized in the isolate
  DartPluginRegistrant.ensureInitialized();

  StreamSubscription<Position>? locationSub;
  bool isTracking = false;

  // Handle commands from the foreground
  service.on('startTracking').listen((_) {
    if (isTracking) return;
    isTracking = true;

    const settings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5,
    );

    locationSub = Geolocator.getPositionStream(locationSettings: settings)
        .listen((position) {
      // Forward position to the foreground UI
      service.invoke('positionUpdate', {
        'lat': position.latitude,
        'lon': position.longitude,
        'alt': position.altitude,
        'speed': position.speed,
        'heading': position.heading,
        'accuracy': position.accuracy,
        'timestamp': position.timestamp.toUtc().toIso8601String(),
      });
    });

    service.invoke('statusUpdate', {'status': 'tracking'});
  });

  service.on('stopTracking').listen((_) {
    locationSub?.cancel();
    locationSub = null;
    isTracking = false;
    service.invoke('statusUpdate', {'status': 'stopped'});
  });

  service.on('updateNotification').listen((data) {
    if (service is AndroidServiceInstance) {
      service.setForegroundNotificationInfo(
        title: data?['title'] ?? 'Aervyx',
        content: data?['content'] ?? 'Tracking',
      );
    }
  });

  service.on('stopService').listen((_) {
    locationSub?.cancel();
    service.stopSelf();
  });
}

/// iOS background handler (required but minimal).
@pragma('vm:entry-point')
Future<bool> _onIosBackground(ServiceInstance service) async {
  DartPluginRegistrant.ensureInitialized();
  return true;
}
