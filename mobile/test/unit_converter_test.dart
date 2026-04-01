import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/utils/unit_converter.dart';

void main() {
  // ═══════════════════════════════════════════════════════════════════════════
  // formatAltitude
  // ═══════════════════════════════════════════════════════════════════════════

  group('formatAltitude', () {
    test('returns metres with "m" unit', () {
      expect(UnitConverter.formatAltitude(1000.0, 'm'), '1000 m');
    });

    test('returns feet with "ft" unit', () {
      // 1000 m * 3.28084 = 3280.84 → "3281 ft"
      expect(UnitConverter.formatAltitude(1000.0, 'ft'), '3281 ft');
    });

    test('rounds to nearest integer', () {
      expect(UnitConverter.formatAltitude(1234.5, 'm'), '1235 m');
    });

    test('handles zero altitude', () {
      expect(UnitConverter.formatAltitude(0.0, 'm'), '0 m');
      expect(UnitConverter.formatAltitude(0.0, 'ft'), '0 ft');
    });

    test('returns -- for null input', () {
      expect(UnitConverter.formatAltitude(null, 'm'), '--');
      expect(UnitConverter.formatAltitude(null, 'ft'), '--');
    });

    test('defaults to metres for unknown unit', () {
      expect(UnitConverter.formatAltitude(500.0, 'furlongs'), '500 m');
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // formatSpeed
  // ═══════════════════════════════════════════════════════════════════════════

  group('formatSpeed', () {
    test('returns km/h with "kph" unit', () {
      // 10 m/s * 3.6 = 36.0
      expect(UnitConverter.formatSpeed(10.0, 'kph'), '36.0 km/h');
    });

    test('returns mph with "mph" unit', () {
      // 10 m/s * 2.23694 = 22.3694 → "22.4 mph"
      expect(UnitConverter.formatSpeed(10.0, 'mph'), '22.4 mph');
    });

    test('returns knots with "kts" unit', () {
      // 10 m/s * 1.94384 = 19.4384 → "19.4 kts"
      expect(UnitConverter.formatSpeed(10.0, 'kts'), '19.4 kts');
    });

    test('handles zero speed', () {
      expect(UnitConverter.formatSpeed(0.0, 'kph'), '0.0 km/h');
    });

    test('returns -- for null input', () {
      expect(UnitConverter.formatSpeed(null, 'kph'), '--');
      expect(UnitConverter.formatSpeed(null, 'mph'), '--');
      expect(UnitConverter.formatSpeed(null, 'kts'), '--');
    });

    test('defaults to kph for unknown unit', () {
      final result = UnitConverter.formatSpeed(10.0, 'parsecs');
      expect(result, contains('km/h'));
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // formatDistance
  // ═══════════════════════════════════════════════════════════════════════════

  group('formatDistance', () {
    test('returns km for large distances with "km" unit', () {
      // 5000 m → "5.0 km"
      expect(UnitConverter.formatDistance(5000.0, 'km'), '5.0 km');
    });

    test('returns metres for short distances with "km" unit', () {
      // 500 m → "500 m" (below 1000m threshold)
      expect(UnitConverter.formatDistance(500.0, 'km'), '500 m');
    });

    test('returns miles for large distances with "mi" unit', () {
      // 5000 m / 1609.344 = 3.1069 → "3.1 mi"
      expect(UnitConverter.formatDistance(5000.0, 'mi'), '3.1 mi');
    });

    test('returns feet for very short distances with "mi" unit', () {
      // 100 m → 100/1609.344 = 0.0621 mi (< 0.1) → falls back to feet
      // 100 * 3.28084 = 328 ft
      expect(UnitConverter.formatDistance(100.0, 'mi'), '328 ft');
    });

    test('returns -- for null input', () {
      expect(UnitConverter.formatDistance(null, 'km'), '--');
      expect(UnitConverter.formatDistance(null, 'mi'), '--');
    });

    test('handles zero distance', () {
      expect(UnitConverter.formatDistance(0.0, 'km'), '0 m');
      expect(UnitConverter.formatDistance(0.0, 'mi'), '0 ft');
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // formatVario
  // ═══════════════════════════════════════════════════════════════════════════

  group('formatVario', () {
    test('returns m/s with "ms" unit', () {
      expect(UnitConverter.formatVario(2.5, 'ms'), '2.5 m/s');
    });

    test('returns fpm with "fpm" unit', () {
      // 2.5 m/s * 196.85 = 492.125 → "492 fpm"
      expect(UnitConverter.formatVario(2.5, 'fpm'), '492 fpm');
    });

    test('handles negative vario (sink)', () {
      expect(UnitConverter.formatVario(-1.5, 'ms'), '-1.5 m/s');
      // -1.5 * 196.85 = -295.275 → "-295 fpm"
      expect(UnitConverter.formatVario(-1.5, 'fpm'), '-295 fpm');
    });

    test('handles zero vario', () {
      expect(UnitConverter.formatVario(0.0, 'ms'), '0.0 m/s');
      expect(UnitConverter.formatVario(0.0, 'fpm'), '0 fpm');
    });

    test('returns -- for null input', () {
      expect(UnitConverter.formatVario(null, 'ms'), '--');
      expect(UnitConverter.formatVario(null, 'fpm'), '--');
    });

    test('defaults to m/s for unknown unit', () {
      final result = UnitConverter.formatVario(1.0, 'unknown');
      expect(result, contains('m/s'));
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // Unit labels
  // ═══════════════════════════════════════════════════════════════════════════

  group('unit labels', () {
    test('altitude unit labels', () {
      expect(UnitConverter.altitudeUnitLabel('m'), 'Metres');
      expect(UnitConverter.altitudeUnitLabel('ft'), 'Feet');
    });

    test('speed unit labels', () {
      expect(UnitConverter.speedUnitLabel('kph'), 'km/hour');
      expect(UnitConverter.speedUnitLabel('mph'), 'Miles/hour');
      expect(UnitConverter.speedUnitLabel('kts'), 'Knots');
    });

    test('distance unit labels', () {
      expect(UnitConverter.distanceUnitLabel('km'), 'Kilometres');
      expect(UnitConverter.distanceUnitLabel('mi'), 'Miles');
    });

    test('vario unit labels', () {
      expect(UnitConverter.varioUnitLabel('ms'), 'Metres/sec');
      expect(UnitConverter.varioUnitLabel('fpm'), 'Feet/min');
    });
  });
}
