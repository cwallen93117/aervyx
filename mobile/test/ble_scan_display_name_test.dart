import 'package:aervyx_mobile/services/api_service.dart';
import 'package:aervyx_mobile/services/ble_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('meshtasticScanDisplayName', () {
    test('prefers platform name', () {
      expect(
        meshtasticScanDisplayName(
          platformName: ' Meshtastic_abcd ',
          advertisedName: 'Advertised',
          remoteId: 'AA:BB:CC:DD:EE:FF',
        ),
        'Meshtastic_abcd',
      );
    });

    test('uses advertised name when platform name is blank', () {
      expect(
        meshtasticScanDisplayName(
          platformName: '',
          advertisedName: ' Mesh_1234 ',
          remoteId: 'AA:BB:CC:DD:EE:FF',
        ),
        'Mesh_1234',
      );
    });

    test('uses remote id fallback when names are blank', () {
      expect(
        meshtasticScanDisplayName(
          platformName: ' ',
          advertisedName: '',
          remoteId: 'AA:BB:CC:DD:EE:FF',
        ),
        'Meshtastic device (AA:BB:CC:DD:EE:FF)',
      );
    });
  });

  group('saved BLE reconnect name', () {
    test('updates from current device short name', () async {
      final ble = BleService(ApiService())
        ..debugSetSavedBleReconnectTarget(
          remoteId: 'AA:BB:CC:DD:EE:FF',
          name: 'OldName',
        );

      await ble.debugRefreshSavedBleReconnectName(' NewShort ');

      expect(ble.savedBleDeviceName, 'NewShort');
    });

    test('ignores blank short names', () async {
      final ble = BleService(ApiService())
        ..debugSetSavedBleReconnectTarget(
          remoteId: 'AA:BB:CC:DD:EE:FF',
          name: 'KeepMe',
        );

      await ble.debugRefreshSavedBleReconnectName(' ');

      expect(ble.savedBleDeviceName, 'KeepMe');
    });
  });
}
