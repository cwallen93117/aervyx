import 'dart:io';

import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'driver_service.dart';

class LocalDriverSosNotifier implements DriverSosNotifier {
  static const _channelId = 'aervyx_driver_sos';
  static const _channelName = 'Driver SOS Alerts';
  static const _channelDescription =
      'Alerts drivers when pilots send active SOS messages.';

  final FlutterLocalNotificationsPlugin _notifications;

  LocalDriverSosNotifier({
    FlutterLocalNotificationsPlugin? notifications,
  }) : _notifications = notifications ?? FlutterLocalNotificationsPlugin();

  Future<void> initialize() async {
    if (!Platform.isAndroid) return;
    const channel = AndroidNotificationChannel(
      _channelId,
      _channelName,
      description: _channelDescription,
      importance: Importance.high,
    );
    await _notifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);
  }

  @override
  Future<void> showSosAlert(DriverSosAlert alert) async {
    if (!Platform.isAndroid) return;
    const details = NotificationDetails(
      android: AndroidNotificationDetails(
        _channelId,
        _channelName,
        channelDescription: _channelDescription,
        importance: Importance.high,
        priority: Priority.high,
        category: AndroidNotificationCategory.alarm,
        visibility: NotificationVisibility.public,
      ),
    );
    final pilotName = alert.displayPilotName;
    final message = (alert.message == null || alert.message!.trim().isEmpty)
        ? 'Pilot needs immediate assistance'
        : alert.message!.trim();
    await _notifications.show(
      alert.id.hashCode & 0x7fffffff,
      'SOS from $pilotName',
      message,
      details,
    );
  }
}
