import 'dart:io';

import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/auth_service.dart';
import 'package:aervyx_mobile/services/igc_service.dart';
import 'package:aervyx_mobile/services/tracking_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:package_info_plus/package_info_plus.dart';

class _FakeApiService extends ApiService {
  final List<String> uploadPaths = [];
  final List<Map<String, String>?> uploadFields = [];
  int postCalls = 0;
  Object? getError;
  Object? postError;

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
  }) async {
    if (getError != null) throw getError!;
    return <String, dynamic>{};
  }

  @override
  Future<Map<String, dynamic>> uploadFile(
    String path, {
    required String filePath,
    String fieldName = 'file',
    Map<String, String>? fields,
  }) async {
    uploadPaths.add(path);
    uploadFields.add(fields);
    return <String, dynamic>{};
  }

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    postCalls += 1;
    if (postError != null) throw postError!;
    return <String, dynamic>{};
  }
}

class _FakeIgcService extends IgcService {
  final String savedPath;

  _FakeIgcService(this.savedPath);

  @override
  int get currentTrackPointCount => 12;

  @override
  Future<String?> saveCurrentFlight({
    String? pilotName,
    int? flightNumber,
  }) async {
    return savedPath;
  }
}

class _RecordingIgcService extends IgcService {
  int recordedPoints = 0;

  @override
  void addTrackPoint(Position pos) {
    recordedPoints += 1;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    PackageInfo.setMockInitialValues(
      appName: 'Aervyx',
      packageName: 'com.aervyx.aervyx_mobile',
      version: '0.4.50',
      buildNumber: '67',
      buildSignature: '',
    );
  });

  test('saved task flight uploads to task endpoint after task state is cleared',
      () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_upload_');
    final igcFile = File('${tempDir.path}/flight.igc')
      ..writeAsStringSync('AXXXAERVYX\n');
    final api = _FakeApiService();
    final tracking = _trackingService(api, _FakeIgcService(igcFile.path));

    await tracking.debugSaveCurrentFlightForUploadTest(42);
    await _waitForUploads(api, 1);

    expect(api.uploadPaths.single, ApiConfig.taskUploadPath(42));
    expect(api.uploadFields.single, {'upload_source': 'app'});
    expect(tracking.error, startsWith('Flight saved'));
    tracking.dispose();
    await tempDir.delete(recursive: true);
  });

  test('saved free flight uploads to logbook endpoint', () async {
    final tempDir = await Directory.systemTemp.createTemp('aervyx_upload_');
    final igcFile = File('${tempDir.path}/flight.igc')
      ..writeAsStringSync('AXXXAERVYX\n');
    final api = _FakeApiService();
    final tracking = _trackingService(api, _FakeIgcService(igcFile.path));

    await tracking.debugSaveCurrentFlightForUploadTest(null);
    await _waitForUploads(api, 1);

    expect(api.uploadPaths.single, ApiConfig.logbookUploadPath);
    expect(api.uploadFields.single, isNull);
    tracking.dispose();
    await tempDir.delete(recursive: true);
  });

  test('successful health check clears stale backend offline error', () async {
    final api = _FakeApiService();
    final tracking = _trackingService(api, IgcService());

    tracking.debugSetBackendOfflineError();
    expect(tracking.error, startsWith('Backend offline'));

    await tracking.debugCheckServerHealth();

    expect(tracking.backendConnected, isTrue);
    expect(tracking.error, isNull);
    tracking.dispose();
  });

  test(
      'background service positions continue IGC recording when backend post fails',
      () async {
    final api = _FakeApiService()..postError = const SocketException('offline');
    final igc = _RecordingIgcService();
    final tracking = _trackingService(api, igc);

    tracking.debugSetTrackingStateForRecordingTest(TrackingState.inFlight);
    await tracking.debugHandleBackgroundPositionForTest({
      'lat': 36.123,
      'lon': -118.456,
      'alt': 1200,
      'speed': 12,
      'heading': 90,
      'accuracy': 4,
      'timestamp': '2026-06-04T18:00:00Z',
    });

    expect(igc.recordedPoints, 1);
    expect(api.postCalls, 1);
    expect(tracking.error, startsWith('Backend offline'));
    expect(tracking.trackingState, TrackingState.inFlight);
    tracking.dispose();
  });
}

TrackingService _trackingService(ApiService api, IgcService igc) {
  final auth = AuthService(api);
  return TrackingService(
    api,
    auth,
    igc,
    sessionDirectoryProvider: () async => Directory.systemTemp,
    preferenceReader: (_) async => null,
    preferenceWriter: (_, __) async {},
  );
}

Future<void> _waitForUploads(_FakeApiService api, int count) async {
  for (var i = 0; i < 20; i++) {
    if (api.uploadPaths.length >= count) return;
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
}
