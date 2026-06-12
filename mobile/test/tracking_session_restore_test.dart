import 'dart:io';

import 'package:aervyx_mobile/models/position.dart' as model;
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/auth_service.dart';
import 'package:aervyx_mobile/services/ble_service.dart';
import 'package:aervyx_mobile/services/igc_service.dart';
import 'package:aervyx_mobile/services/tracking_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _FakeApiService extends ApiService {}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: 'Aervyx',
      packageName: 'com.aervyx.aervyx_mobile',
      version: '0.4.43',
      buildNumber: '60',
      buildSignature: '',
    );
  });

  test('tracking session snapshot round-trips active pre-flight state', () {
    final savedAt = DateTime.parse('2026-05-31T12:00:00Z');
    final lastPositionTime = DateTime.parse('2026-05-31T12:00:05Z');
    final snapshot = TrackingSessionSnapshot(
      trackingState: TrackingState.preFlight,
      savedAt: savedAt,
      trackingStartTime: null,
      positionCount: 7,
      flightNumberToday: 1,
      takeoffLat: 35.1,
      takeoffLon: -82.2,
      driverMode: false,
      debugMode: false,
      multiFlightEnabled: true,
      lastPosition: model.Position(
        lat: 35.2,
        lon: -82.3,
        alt: 901,
        speed: 1.2,
        heading: 180,
        accuracy: 4,
        timestamp: lastPositionTime,
      ),
    );

    final restored = TrackingSessionSnapshot.fromJson(snapshot.toJson());

    expect(restored.trackingState, TrackingState.preFlight);
    expect(restored.positionCount, 7);
    expect(restored.flightNumberToday, 1);
    expect(restored.multiFlightEnabled, isTrue);
    expect(restored.lastPosition?.lat, 35.2);
    expect(restored.lastPosition?.timestamp, lastPositionTime);
  });

  test('restoreActiveSession restores pre-flight instead of idle', () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_tracking_');
    final tracking = _trackingService(tempDir);

    await tracking.debugSaveTrackingSessionSnapshot(
      TrackingSessionSnapshot(
        trackingState: TrackingState.preFlight,
        savedAt: DateTime.now().toUtc(),
        trackingStartTime: null,
        positionCount: 0,
        flightNumberToday: 1,
        takeoffLat: null,
        takeoffLon: null,
        driverMode: false,
        debugMode: false,
        multiFlightEnabled: true,
        lastPosition: null,
      ),
    );

    await tracking.restoreActiveSession(restartRuntimeServices: false);

    expect(tracking.trackingState, TrackingState.preFlight);
    expect(tracking.isPreFlight, isTrue);
    await tempDir.delete(recursive: true);
  });

  test('restoreActiveSession clears stale snapshots', () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_tracking_');
    final tracking = _trackingService(tempDir);

    await tracking.debugSaveTrackingSessionSnapshot(
      TrackingSessionSnapshot(
        trackingState: TrackingState.inFlight,
        savedAt: DateTime.now().toUtc().subtract(const Duration(hours: 19)),
        trackingStartTime:
            DateTime.now().toUtc().subtract(const Duration(hours: 20)),
        positionCount: 10,
        flightNumberToday: 1,
        takeoffLat: 35.1,
        takeoffLon: -82.2,
        driverMode: false,
        debugMode: false,
        multiFlightEnabled: true,
        lastPosition: null,
      ),
    );

    await tracking.restoreActiveSession(restartRuntimeServices: false);

    expect(tracking.trackingState, TrackingState.idle);
    expect(await tracking.debugTrackingSessionExists(), isFalse);
    await tempDir.delete(recursive: true);
  });

  test('restoreActiveSession clears malformed snapshots', () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_tracking_');
    final tracking = _trackingService(tempDir);

    await tracking.debugWriteRawTrackingSession('{not-json');
    await tracking.restoreActiveSession(restartRuntimeServices: false);

    expect(tracking.trackingState, TrackingState.idle);
    expect(await tracking.debugTrackingSessionExists(), isFalse);
    await tempDir.delete(recursive: true);
  });

  test('tracking mesh reconnect requester is forced and success is quiet',
      () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_tracking_');
    final calls = <bool>[];
    final tracking = _trackingService(
      tempDir,
      meshReconnectRequester: ({bool force = false}) async {
        calls.add(force);
        return const BleReconnectResult(BleReconnectStatus.connected);
      },
    );

    await tracking.debugRequestMeshReconnectForTracking();

    expect(calls, [true]);
    expect(tracking.meshReconnectWarning, isNull);
    await tempDir.delete(recursive: true);
  });

  test('tracking preserves non-fatal mesh reconnect warning on failure',
      () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_tracking_');
    final tracking = _trackingService(
      tempDir,
      meshReconnectRequester: ({bool force = false}) async {
        return const BleReconnectResult(BleReconnectStatus.notFound);
      },
    );

    await tracking.debugRequestMeshReconnectForTracking();

    expect(
      tracking.meshReconnectWarning,
      contains('saved Meshtastic device was not found'),
    );
    expect(tracking.error, isNull);
    await tempDir.delete(recursive: true);
  });
}

TrackingService _trackingService(
  Directory sessionDir, {
  MeshReconnectRequester? meshReconnectRequester,
}) {
  final api = _FakeApiService();
  final auth = AuthService(api);
  final igc = IgcService();
  return TrackingService(
    api,
    auth,
    igc,
    sessionDirectoryProvider: () async => sessionDir,
    meshReconnectRequester: meshReconnectRequester,
    preferenceReader: (_) async => null,
    preferenceWriter: (_, __) async {},
  );
}
