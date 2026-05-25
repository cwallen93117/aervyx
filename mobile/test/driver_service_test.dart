import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/driver_service.dart';
import 'package:flutter_test/flutter_test.dart';

class FakeDriverApiService extends ApiService {
  var activeTaskCalls = 0;
  var sseOpened = false;

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
  });
}
