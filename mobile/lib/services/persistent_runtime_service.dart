import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

/// Controls the Android foreground runtime that keeps Aervyx alive after launch.
///
/// This service is intentionally separate from the GPS tracking background
/// service so the app can stay alive while idle or waiting for takeoff without
/// requiring location foreground-service privileges.
class PersistentRuntimeService {
  static const MethodChannel _channel = MethodChannel(
    'com.aervyx.aervyx_mobile/persistent_runtime',
  );

  static Future<void> requestNotificationPermission() async {
    if (!Platform.isAndroid) return;
    final notifications = FlutterLocalNotificationsPlugin()
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>();
    await notifications?.requestNotificationsPermission();
  }

  static Future<void> start() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('start');
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('stop');
  }

  static Future<void> pauseForTracking() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('pauseForTracking');
  }

  static Future<void> resumeAfterTracking() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('resumeAfterTracking');
  }

  static Future<void> setBleActive(bool active) async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('setBleActive', {'active': active});
  }

  static Future<void> setLocationActive(bool active) async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('setLocationActive', {'active': active});
  }

  static Future<void> setAutoExitBatteryThreshold(int? threshold) async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>(
      'setAutoExitBatteryThreshold',
      {'threshold': threshold},
    );
  }

  static Future<int?> getAutoExitBatteryThreshold() async {
    if (!Platform.isAndroid) return null;
    return _channel.invokeMethod<int>('getAutoExitBatteryThreshold');
  }

  static Future<int?> getBatteryLevel() async {
    if (!Platform.isAndroid) return null;
    return _channel.invokeMethod<int>('getBatteryLevel');
  }

  static Future<bool?> isBatteryCharging() async {
    if (!Platform.isAndroid) return null;
    return _channel.invokeMethod<bool>('isBatteryCharging');
  }

  static Future<bool> get isEnabled async {
    if (!Platform.isAndroid) return false;
    return await _channel.invokeMethod<bool>('isEnabled') ?? false;
  }

  static Future<void> openBatteryOptimizationSettings() async {
    if (!Platform.isAndroid) return;
    await _channel.invokeMethod<bool>('openBatteryOptimizationSettings');
  }
}
