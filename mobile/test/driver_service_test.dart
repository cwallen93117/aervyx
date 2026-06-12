import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/driver_service.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeDriverApiService extends ApiService {
  var activeTaskCalls = 0;
  var activePilotCalls = 0;
  var sosCalls = 0;
  var sseOpened = false;
  List<dynamic> activePilots = <dynamic>[];
  List<dynamic> sosAlerts = <dynamic>[];

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
    if (path == ApiConfig.driverSosAlertsPath) {
      sosCalls += 1;
      return sosAlerts;
    }
    return <dynamic>[];
  }

  @override
  Stream<String> sseStream(String path) {
    sseOpened = true;
    return const Stream<String>.empty();
  }
}

class FakeDriverSosNotifier implements DriverSosNotifier {
  final shown = <DriverSosAlert>[];

  @override
  Future<void> showSosAlert(DriverSosAlert alert) async {
    shown.add(alert);
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
          'pilot_id': 3,
          'pilot_name': 'Alex Able',
          'lat': 35.0,
          'lon': -82.1,
          'profile_type': 'pilot',
          'timestamp': '2026-05-28T12:00:05Z',
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
    expect(service.visiblePilots, hasLength(2));
    expect(service.visiblePilots.map((pilot) => pilot.name), [
      'Alex Able',
      'Pat Pilot',
    ]);
    expect(service.visiblePilots.last.pilotId, 7);
    expect(service.connected, isFalse);
    service.dispose();
  });

  test('connect polls SOS alerts and deduplicates local notifications',
      () async {
    final api = FakeDriverApiService()
      ..sosAlerts = [
        {
          'id': 'alert-1',
          'pilot_id': 7,
          'pilot_name': 'Pat Pilot',
          'lat': 35.1,
          'lon': -82.2,
          'alt': 900,
          'message': 'Need retrieve help',
          'timestamp': '2026-05-28T12:00:00Z',
          'status': 'active',
        },
      ];
    final notifier = FakeDriverSosNotifier();
    final service = DriverService(api, sosNotifier: notifier);

    await service.connect();
    await service.connect();

    expect(api.sosCalls, 2);
    expect(service.activeSosAlerts, hasLength(1));
    expect(service.activeSosAlerts.single.displayPilotName, 'Pat Pilot');
    expect(notifier.shown, hasLength(1));
    expect(notifier.shown.single.id, 'alert-1');
    service.dispose();
  });
}
