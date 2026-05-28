import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/driver_service.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeDriverApiService extends ApiService {
  var activeTaskCalls = 0;
  var activePilotCalls = 0;
  var sseOpened = false;
  List<dynamic> activePilots = <dynamic>[];

  @override
  Future<Map<String, dynamic>> get(
    String path, {
    Map<String, String>? query,
  }) async {
    expect(path, ApiConfig.activeTaskPath);
    activeTaskCalls += 1;
    return <String, dynamic>{};
  }

  @override
  Future<List<dynamic>> getList(
    String path, {
    Map<String, String>? query,
  }) async {
    if (path == ApiConfig.activePilotsPath) {
      activePilotCalls += 1;
      return activePilots;
    }
    return <dynamic>[];
  }

  @override
  Stream<String> sseStream(String path) {
    sseOpened = true;
    return const Stream<String>.empty();
  }
}

void main() {
  test('connect allows driver mode without an active task', () async {
    final api = FakeDriverApiService();
    final service = DriverService(api);

    await service.connect();

    expect(api.activeTaskCalls, 1);
    expect(api.sseOpened, isFalse);
    expect(service.error, isNull);
    expect(service.taskId, isNull);
    expect(service.hasActiveTask, isFalse);
    expect(service.connected, isFalse);
    expect(service.pilots, isEmpty);
    service.dispose();
  });

  test('connect shows all active pilots when driver has no active task',
      () async {
    final api = FakeDriverApiService()
      ..activePilots = [
        {
          'pilot_id': 7,
          'pilot_name': 'Pat Pilot',
          'lat': 35.1,
          'lon': -82.2,
          'alt': 900,
          'speed': 12,
          'aircraft_icon': 'hang_glider',
          'profile_type': 'pilot',
          'timestamp': '2026-05-28T12:00:00Z',
        },
        {
          'user_id': 11,
          'pilot_name': 'Dana Driver',
          'lat': 35.2,
          'lon': -82.3,
          'profile_type': 'driver',
          'timestamp': '2026-05-28T12:00:00Z',
        },
      ];
    final service = DriverService(api);

    await service.connect();

    expect(api.activePilotCalls, 1);
    expect(service.visiblePilots, hasLength(1));
    expect(service.visiblePilots.single.name, 'Pat Pilot');
    expect(service.visiblePilots.single.pilotId, 7);
    expect(service.connected, isFalse);
    service.dispose();
  });
}
