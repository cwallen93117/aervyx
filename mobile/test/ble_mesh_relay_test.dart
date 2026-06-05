import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/models/meshtastic_protobufs.dart';
import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/ble_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('BleService mesh relay', () {
    test('posts peer mesh positions when not recording', () async {
      final api = _RecordingApiService();
      final ble = BleService(api);
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(_positionPacket(fromNode: 0x0a0b0c0d));

      expect(api.posts, hasLength(1));
      expect(api.posts.single.path, ApiConfig.trackPositionPath);
      expect(api.posts.single.body['source'], 'mesh_relay');
      expect(api.posts.single.body['device_id'], '!0a0b0c0d');
      expect(api.posts.single.body['lat'], closeTo(37.1234567, 0.0000001));
      expect(api.posts.single.body['lon'], closeTo(-122.7654321, 0.0000001));
    });

    test('keeps own node positions local instead of posting them', () async {
      final api = _RecordingApiService();
      final ble = BleService(api);
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(_positionPacket(fromNode: 0x01020304));

      expect(api.posts, isEmpty);
      expect(ble.deviceHasGpsFix, isTrue);
      expect(ble.deviceGpsLat, closeTo(37.1234567, 0.0000001));
      expect(ble.deviceGpsLon, closeTo(-122.7654321, 0.0000001));
    });

    test('blocks peer mesh relay at or below the battery threshold', () async {
      final api = _RecordingApiService();
      final ble = BleService(
        api,
        batteryThresholdProvider: () => 15,
        batteryLevelProvider: () async => 15,
      );
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(_positionPacket(fromNode: 0x0a0b0c0d));

      expect(api.posts, isEmpty);
    });

    test('allows peer mesh relay when the battery guard is disabled', () async {
      final api = _RecordingApiService();
      final ble = BleService(
        api,
        batteryThresholdProvider: () => null,
        batteryLevelProvider: () async => 5,
      );
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(_positionPacket(fromNode: 0x0a0b0c0d));

      expect(api.posts, hasLength(1));
    });

    test('allows peer mesh relay when battery level cannot be read', () async {
      final api = _RecordingApiService();
      final ble = BleService(
        api,
        batteryThresholdProvider: () => 15,
        batteryLevelProvider: () async => null,
      );
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(_positionPacket(fromNode: 0x0a0b0c0d));

      expect(api.posts, hasLength(1));
    });

    test('posts own radio battery telemetry with received timestamp', () async {
      final api = _RecordingApiService();
      final ble = BleService(api);
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(
        _telemetryPacket(fromNode: 0x01020304, batteryLevel: 88),
      );

      expect(ble.deviceBatteryLevel, 88);
      expect(ble.deviceBatteryLevelReceivedAt, isNotNull);
      expect(api.posts, hasLength(1));
      expect(api.posts.single.path, ApiConfig.meshRadioTelemetryPath);
      expect(api.posts.single.body['device_id'], '!01020304');
      expect(api.posts.single.body['battery_level'], 88);
      expect(
        DateTime.tryParse(
          api.posts.single.body['battery_level_seen_at'] as String,
        ),
        isNotNull,
      );
    });

    test('ignores peer telemetry for connected radio battery reporting',
        () async {
      final api = _RecordingApiService();
      final ble = BleService(api);
      ble.deviceState.myNodeNum = 0x01020304;

      await ble.debugHandleMeshPacket(
        _telemetryPacket(fromNode: 0x0a0b0c0d, batteryLevel: 44),
      );

      expect(ble.deviceBatteryLevel, isNull);
      expect(ble.deviceBatteryLevelReceivedAt, isNull);
      expect(api.posts, isEmpty);
    });
  });

  group('BleService auto-reconnect', () {
    test('forced reconnect uses direct saved-device connect', () async {
      final api = _RecordingApiService();
      final calls = <String>[];
      final ble = BleService(
        api,
        debugDirectReconnectHandler: (remoteId, name) async {
          calls.add('$remoteId|$name');
          return const BleReconnectResult(BleReconnectStatus.connected);
        },
      )..debugSetSavedBleReconnectTarget(
          remoteId: 'AA:BB:CC:DD:EE:FF',
          name: 'Meshtastic_1234',
        );

      final result = await ble.restoreAutoReconnect(force: true);

      expect(result.status, BleReconnectStatus.connected);
      expect(calls, ['AA:BB:CC:DD:EE:FF|Meshtastic_1234']);
    });

    test('passive reconnect respects disabled auto-reconnect target', () async {
      final api = _RecordingApiService();
      var directCalls = 0;
      final ble = BleService(
        api,
        debugDirectReconnectHandler: (_, __) async {
          directCalls++;
          return const BleReconnectResult(BleReconnectStatus.connected);
        },
      )..debugSetSavedBleReconnectTarget(
          remoteId: 'AA:BB:CC:DD:EE:FF',
          autoReconnectEnabled: false,
        );

      final result = await ble.restoreAutoReconnect();

      expect(result.status, BleReconnectStatus.noSavedDevice);
      expect(directCalls, 0);
    });

    test('forced reconnect falls back after direct saved-device failure',
        () async {
      final api = _RecordingApiService();
      var directCalls = 0;
      var discoveryCalls = 0;
      final ble = BleService(
        api,
        debugDirectReconnectHandler: (_, __) async {
          directCalls++;
          return const BleReconnectResult(
            BleReconnectStatus.failed,
            message: 'direct failed',
          );
        },
        debugDiscoveryReconnectHandler: () async {
          discoveryCalls++;
          return const BleReconnectResult(BleReconnectStatus.connected);
        },
      )..debugSetSavedBleReconnectTarget(
          remoteId: 'AA:BB:CC:DD:EE:FF',
          name: 'Meshtastic_1234',
        );

      final result = await ble.restoreAutoReconnect(force: true);

      expect(result.status, BleReconnectStatus.connected);
      expect(directCalls, 1);
      expect(discoveryCalls, 1);
    });

    test('concurrent forced reconnect requests share one direct attempt',
        () async {
      final api = _RecordingApiService();
      final completer = Completer<BleReconnectResult>();
      var directCalls = 0;
      final ble = BleService(
        api,
        debugDirectReconnectHandler: (_, __) {
          directCalls++;
          return completer.future;
        },
      )..debugSetSavedBleReconnectTarget(remoteId: 'AA:BB:CC:DD:EE:FF');

      final first = ble.restoreAutoReconnect(force: true);
      final second = ble.restoreAutoReconnect(force: true);
      completer.complete(
        const BleReconnectResult(BleReconnectStatus.connected),
      );

      expect((await first).status, BleReconnectStatus.connected);
      expect((await second).status, BleReconnectStatus.connected);
      expect(directCalls, 1);
    });
  });
}

Uint8List _positionPacket({
  required int fromNode,
  double lat = 37.1234567,
  double lon = -122.7654321,
  int time = 1714000000,
}) {
  final position = ProtoWriter()
    ..writeSfixed32(1, (lat * 1e7).round())
    ..writeSfixed32(2, (lon * 1e7).round())
    ..writeVarint(3, 123)
    ..writeFixed32(4, time)
    ..writeVarint(8, 42)
    ..writeVarint(9, 9000000);

  final decoded = ProtoWriter()
    ..writeVarint(1, PortNum.positionApp)
    ..writeBytes(2, position.toBytes());

  return (ProtoWriter()
        ..writeFixed32(1, fromNode)
        ..writeMessage(4, decoded))
      .toBytes();
}

Uint8List _telemetryPacket({
  required int fromNode,
  required int batteryLevel,
}) {
  final deviceMetrics = ProtoWriter()..writeVarint(1, batteryLevel);
  final telemetry = ProtoWriter()..writeMessage(2, deviceMetrics);
  final decoded = ProtoWriter()
    ..writeVarint(1, 67)
    ..writeBytes(2, telemetry.toBytes());

  return (ProtoWriter()
        ..writeFixed32(1, fromNode)
        ..writeMessage(4, decoded))
      .toBytes();
}

class _RecordingApiService extends ApiService {
  final List<_PostCall> posts = [];

  @override
  Future<Map<String, dynamic>> post(
    String path, {
    Map<String, dynamic>? body,
  }) async {
    posts.add(_PostCall(path, Map<String, dynamic>.from(body ?? {})));
    return {};
  }
}

class _PostCall {
  final String path;
  final Map<String, dynamic> body;

  const _PostCall(this.path, this.body);
}
