import 'dart:async';
import 'dart:typed_data';

import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../mesh_transport.dart';

/// Meshtastic BLE service and characteristic UUIDs.
const String meshServiceUuid = '6ba1b218-15a8-461f-9fa8-5dcae273eafd';
const String toRadioCharUuid = 'f75c76d2-129e-4dad-a1dd-7866124401e7';
const String fromRadioCharUuid = '2c55e69e-4993-11ed-b878-0242ac120002';
const String fromNumCharUuid = 'ed9da18c-a800-4f66-a670-aa7547e34453';

/// BLE transport — wraps GATT characteristic read/write behind [MeshTransport].
class BleTransport implements MeshTransport {
  final BluetoothDevice _device;
  final BluetoothCharacteristic _toRadio;
  final BluetoothCharacteristic _fromRadio;
  final BluetoothCharacteristic? _fromNum;

  bool _connected = true;
  StreamController<void>? _dataAvailableController;
  StreamSubscription<List<int>>? _fromNumSubscription;

  BleTransport({
    required BluetoothDevice device,
    required BluetoothCharacteristic toRadio,
    required BluetoothCharacteristic fromRadio,
    BluetoothCharacteristic? fromNum,
  })  : _device = device,
        _toRadio = toRadio,
        _fromRadio = fromRadio,
        _fromNum = fromNum;

  @override
  ConnectionType get type => ConnectionType.ble;

  @override
  String get connectionLabel => _device.platformName.isNotEmpty
      ? _device.platformName
      : _device.remoteId.toString();

  @override
  bool get isConnected => _connected;

  @override
  Future<void> writeToRadio(Uint8List data) async {
    await _toRadio.write(data, withoutResponse: false);
  }

  @override
  Future<Uint8List> readFromRadio() async {
    final data = await _fromRadio.read();
    return Uint8List.fromList(data);
  }

  @override
  Stream<void>? get onDataAvailable {
    if (_fromNum == null) return null;
    // Lazily set up fromNum notifications
    if (_dataAvailableController == null) {
      _dataAvailableController = StreamController<void>.broadcast();
      _fromNum.setNotifyValue(true).then((_) {
        _fromNumSubscription = _fromNum.onValueReceived.listen((_) {
          _dataAvailableController?.add(null);
        });
      }).catchError((_) {
        // Notifications not supported — caller will fall back to polling
      });
    }
    return _dataAvailableController!.stream;
  }

  @override
  Future<void> disconnect() async {
    _connected = false;
    _fromNumSubscription?.cancel();
    _fromNumSubscription = null;
    _dataAvailableController?.close();
    _dataAvailableController = null;
    try {
      await _device.disconnect();
    } catch (_) {}
  }

  /// Mark the transport as disconnected externally (e.g. unexpected BLE drop).
  void markDisconnected() {
    _connected = false;
    _fromNumSubscription?.cancel();
    _fromNumSubscription = null;
    _dataAvailableController?.close();
    _dataAvailableController = null;
  }
}
