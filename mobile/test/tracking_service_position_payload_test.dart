import 'package:aervyx_mobile/services/tracking_service.dart';
import 'package:aervyx_mobile/services/background_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('app position payload includes phone battery when known', () {
    final batterySeenAt = DateTime.parse('2026-05-29T12:00:30Z');

    final payload = TrackingService.debugBuildPositionPayloadFromValues(
      _position(),
      batteryLevel: 87,
      batteryLevelSeenAt: batterySeenAt,
    );

    expect(payload['source'], 'app');
    expect(payload['battery_level'], 87);
    expect(payload['battery_level_seen_at'], batterySeenAt.toIso8601String());
  });

  test('app position payload omits phone battery when unavailable', () {
    final payload = TrackingService.debugBuildPositionPayloadFromValues(
      _position(),
    );

    expect(payload.containsKey('battery_level'), isFalse);
    expect(payload.containsKey('battery_level_seen_at'), isFalse);
  });

  test('free-flight location settings match dense event tracking', () {
    final freeFlight = TrackingService.debugLocationSettingsForTrackingMode(
      driverMode: false,
      hasActiveTask: false,
      debugMode: false,
    );
    final eventFlight = TrackingService.debugLocationSettingsForTrackingMode(
      driverMode: false,
      hasActiveTask: true,
      debugMode: false,
    );

    expect(freeFlight.accuracy, LocationAccuracy.best);
    expect(freeFlight.distanceFilter, 0);
    expect(eventFlight.accuracy, freeFlight.accuracy);
    expect(eventFlight.distanceFilter, freeFlight.distanceFilter);
  });

  test('background tracking uses dense GPS settings', () {
    expect(BackgroundTrackingService.trackingLocationSettings.accuracy,
        LocationAccuracy.best);
    expect(
        BackgroundTrackingService.trackingLocationSettings.distanceFilter, 0);
  });
}

Position _position() {
  return Position(
    latitude: 40.0547,
    longitude: -75.3516,
    timestamp: DateTime.parse('2026-05-29T12:00:00Z'),
    accuracy: 3,
    altitude: 40,
    altitudeAccuracy: 1,
    heading: 0,
    headingAccuracy: 1,
    speed: 0.1,
    speedAccuracy: 0.1,
  );
}
