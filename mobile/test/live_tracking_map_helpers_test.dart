import 'package:aervyx_mobile/widgets/live_tracking_map_helpers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('liveShortName includes first name and last initial', () {
    expect(liveShortName('Mick Howard'), 'Mick H.');
    expect(liveShortName('  Leonardo   Ortiz  '), 'Leonardo O.');
    expect(liveShortName('Tracker'), 'Tracker');
    expect(liveShortName(''), 'Tracker');
  });

  test('liveColorForSubject follows the Watch Live palette order', () {
    final keys = ['pilot:1', 'pilot:2', 'pilot:3'];
    expect(liveColorForSubject('pilot:1', keys), const Color(0xFF2563EB));
    expect(liveColorForSubject('pilot:2', keys), const Color(0xFFDC2626));
    expect(liveColorForSubject('pilot:3', keys), const Color(0xFF16A34A));
  });

  test('liveRelativeTime formats compact last seen labels', () {
    final now = DateTime(2026, 5, 28, 12);
    expect(liveRelativeTime(now.subtract(const Duration(seconds: 5)), now: now),
        'just now');
    expect(
        liveRelativeTime(now.subtract(const Duration(seconds: 25)), now: now),
        '25s ago');
    expect(liveRelativeTime(now.subtract(const Duration(minutes: 8)), now: now),
        '8m ago');
    expect(liveRelativeTime(now.subtract(const Duration(hours: 2)), now: now),
        '2h ago');
  });

  test('stale positions begin after five minutes', () {
    final now = DateTime(2026, 5, 28, 12);
    expect(
        isLivePositionStale(now.subtract(const Duration(minutes: 4)), now: now),
        isFalse);
    expect(
        isLivePositionStale(now.subtract(const Duration(minutes: 5)), now: now),
        isTrue);
  });

  test('mesh positions use dashed marker borders', () {
    expect(livePositionSourceUsesDashedBorder('mesh'), isTrue);
    expect(livePositionSourceUsesDashedBorder('cellular'), isFalse);
    expect(livePositionSourceUsesDashedBorder('other'), isFalse);
    expect(livePositionSourceUsesDashedBorder(null), isFalse);
  });

  test('directions URIs target default map apps with web fallback', () {
    expect(
      liveDirectionsGeoUri(35.1, -82.2, label: 'Pat Pilot').toString(),
      'geo:35.1,-82.2?q=35.1,-82.2(Pat%20Pilot)',
    );
    expect(
      liveDirectionsWebUri(35.1, -82.2).toString(),
      'https://www.google.com/maps/search/?api=1&query=35.1%2C-82.2',
    );
  });
}
