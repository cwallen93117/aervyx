// Smoke tests that verify the test runner works and key enums/utilities
// are available. We intentionally avoid instantiating AervyxApp here because
// it requires MultiProvider with live services, BLE, GPS, etc.

import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/services/tracking_service.dart';
import 'package:aervyx_mobile/utils/unit_converter.dart';

void main() {
  group('TrackingState enum', () {
    test('has all expected values', () {
      expect(TrackingState.values.length, 4);
      expect(TrackingState.values, contains(TrackingState.idle));
      expect(TrackingState.values, contains(TrackingState.preFlight));
      expect(TrackingState.values, contains(TrackingState.inFlight));
      expect(TrackingState.values, contains(TrackingState.monitoring));
    });
  });

  group('TrackingZone enum', () {
    test('has all expected values', () {
      expect(TrackingZone.values.length, 4);
      expect(TrackingZone.values, contains(TrackingZone.stationary));
      expect(TrackingZone.values, contains(TrackingZone.normalFlight));
      expect(TrackingZone.values, contains(TrackingZone.approaching));
      expect(TrackingZone.values, contains(TrackingZone.critical));
    });
  });

  group('SportType enum', () {
    test('has all expected values', () {
      expect(SportType.values.length, 3);
      expect(SportType.values, contains(SportType.paraglider));
      expect(SportType.values, contains(SportType.hangGlider));
      expect(SportType.values, contains(SportType.glider));
    });
  });

  group('UnitConverter basic sanity', () {
    test('formatAltitude returns non-empty string for valid input', () {
      final result = UnitConverter.formatAltitude(1000.0, 'm');
      expect(result, isNotEmpty);
      expect(result, contains('m'));
    });

    test('formatSpeed returns non-empty string for valid input', () {
      final result = UnitConverter.formatSpeed(10.0, 'kph');
      expect(result, isNotEmpty);
      expect(result, contains('km/h'));
    });

    test('formatVario returns non-empty string for valid input', () {
      final result = UnitConverter.formatVario(2.5, 'ms');
      expect(result, isNotEmpty);
      expect(result, contains('m/s'));
    });
  });
}
