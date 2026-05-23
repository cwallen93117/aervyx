import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../services/background_service.dart';
import '../services/ble_service.dart';
import '../services/driver_service.dart';
import '../services/persistent_runtime_service.dart';
import '../services/tracking_service.dart';

Future<void> confirmAppShutdown(BuildContext context) async {
  final shouldShutdown = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => AlertDialog(
      title: const Text('Shut down Aervyx?'),
      content: const Text(
        'This stops the persistent runtime, Bluetooth, GPS tracking, and the '
        'ongoing notification until you open the app again.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(dialogContext).pop(false),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: () => Navigator.of(dialogContext).pop(true),
          icon: const Icon(Icons.power_settings_new),
          label: const Text('Shut Down'),
        ),
      ],
    ),
  );

  if (shouldShutdown == true && context.mounted) {
    await shutDownApp(context);
  }
}

Future<void> shutDownApp(BuildContext context) async {
  final tracking = context.read<TrackingService>();
  final ble = context.read<BleService>();
  final driver = context.read<DriverService>();

  try {
    if (tracking.isTracking) {
      await tracking.stopTracking();
    }
  } catch (_) {}

  try {
    await ble.disconnect();
  } catch (_) {}

  try {
    driver.disconnect();
  } catch (_) {}

  try {
    await BackgroundTrackingService.stop();
  } catch (_) {}

  try {
    await PersistentRuntimeService.setBleActive(false);
    await PersistentRuntimeService.setLocationActive(false);
    await PersistentRuntimeService.stop();
  } catch (_) {}

  await SystemNavigator.pop();
}
