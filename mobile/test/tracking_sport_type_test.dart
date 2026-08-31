import 'dart:io';

import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/auth_service.dart';
import 'package:aervyx_mobile/services/igc_service.dart';
import 'package:aervyx_mobile/services/tracking_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _FakeApiService extends ApiService {
  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
  }) async {
    return <String, dynamic>{};
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: 'Aervyx',
      packageName: 'com.aervyx.aervyx_mobile',
      version: '0.4.57',
      buildNumber: '74',
      buildSignature: '',
    );
  });

  test('defaults to hang glider when no saved sport type exists', () async {
    final tracking = _trackingService(<String, String>{});

    expect(tracking.sportType, SportType.hangGlider);
    await Future<void>.delayed(Duration.zero);
    tracking.dispose();
  });

  test('saves selected sport type and restores it on reload', () async {
    final preferences = <String, String>{};
    final tracking = _trackingService(preferences);

    tracking.setSportType(SportType.glider);
    await Future<void>.delayed(Duration.zero);

    final restored = _trackingService(preferences);
    await restored.debugLoadSportTypePreference();

    expect(preferences['tracking_sport_type'], 'glider');
    expect(restored.sportType, SportType.glider);
    await Future<void>.delayed(Duration.zero);
    tracking.dispose();
    restored.dispose();
  });

  test('applies nested backend takeoff thresholds by selected sport', () async {
    final tracking = _trackingService(<String, String>{});

    tracking.applyAdminSettings({
      'paraglider': {
        'altitude_gain_m': 11,
        'speed_threshold_ms': 2.4,
      },
      'hang_glider': {
        'altitude_gain_m': 12,
        'speed_threshold_ms': 3.8,
      },
      'glider': {
        'altitude_gain_m': 16,
        'speed_threshold_ms': 6.9,
      },
      'landing_speed_ms': 4.5,
      'landing_altitude_tolerance_m': 31,
      'landing_confirm_seconds': 16,
      'landing_countdown_seconds': 17,
    });

    expect(tracking.debugTakeoffAltitudeGainMeters, 12);
    expect(tracking.debugTakeoffSpeedThresholdMs, 3.8);

    tracking.setSportType(SportType.paraglider);
    expect(tracking.debugTakeoffAltitudeGainMeters, 11);
    expect(tracking.debugTakeoffSpeedThresholdMs, 2.4);

    tracking.setSportType(SportType.glider);
    expect(tracking.debugTakeoffAltitudeGainMeters, 16);
    expect(tracking.debugTakeoffSpeedThresholdMs, 6.9);
    await Future<void>.delayed(Duration.zero);
    tracking.dispose();
  });

  test('multi-flight monitoring remains available until 10 PM local time',
      () async {
    final tracking = _trackingService(<String, String>{});

    expect(
      tracking.debugIsMonitoringEligibleAt(DateTime(2026, 8, 31, 21, 59)),
      isTrue,
    );
    expect(
      tracking.debugIsMonitoringEligibleAt(DateTime(2026, 8, 31, 22)),
      isFalse,
    );
    await Future<void>.delayed(Duration.zero);
    tracking.dispose();
  });
}

TrackingService _trackingService(Map<String, String> preferences) {
  final api = _FakeApiService();
  return TrackingService(
    api,
    AuthService(api),
    IgcService(),
    sessionDirectoryProvider: () async => Directory.systemTemp,
    preferenceReader: (key) async => preferences[key],
    preferenceWriter: (key, value) async {
      preferences[key] = value;
    },
  );
}
