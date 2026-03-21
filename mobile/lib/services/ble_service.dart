import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';

import '../models/mesh_config.dart';
import '../config/api_config.dart';
import 'api_service.dart';

/// Meshtastic BLE service UUID (standard Meshtastic BLE API).
const String _meshtasticServiceUuid = '6ba1b218-15a8-461f-9fa8-5dcae273eafd';

/// Meshtastic toRadio characteristic — used to write configuration.
const String _toRadioCharUuid = 'f75c76d2-129e-4dad-a1dd-7866124401e7';

/// Meshtastic fromRadio characteristic — used to read responses.
const String _fromRadioCharUuid = '2c55e69e-4993-11ed-b878-0242ac120002';

/// Represents a discovered Meshtastic device.
class MeshtasticDevice {
  final BluetoothDevice device;
  final String name;
  final int rssi;

  const MeshtasticDevice({
    required this.device,
    required this.name,
    required this.rssi,
  });
}

/// BLE service for scanning, pairing with, and configuring Meshtastic radios.
class BleService extends ChangeNotifier {
  final ApiService _api;

  List<MeshtasticDevice> _discoveredDevices = [];
  MeshtasticDevice? _connectedDevice;
  bool _isScanning = false;
  bool _isConnecting = false;
  bool _isPushingConfig = false;
  String? _error;
  String? _statusMessage;
  StreamSubscription<List<ScanResult>>? _scanSubscription;

  List<MeshtasticDevice> get discoveredDevices => _discoveredDevices;
  MeshtasticDevice? get connectedDevice => _connectedDevice;
  bool get isScanning => _isScanning;
  bool get isConnecting => _isConnecting;
  bool get isPushingConfig => _isPushingConfig;
  String? get error => _error;
  String? get statusMessage => _statusMessage;

  BleService(this._api);

  /// Start scanning for Meshtastic BLE devices.
  Future<void> startScan({Duration timeout = const Duration(seconds: 10)}) async {
    if (_isScanning) return;

    _isScanning = true;
    _discoveredDevices = [];
    _error = null;
    notifyListeners();

    try {
      await FlutterBluePlus.startScan(
        withServices: [Guid(_meshtasticServiceUuid)],
        timeout: timeout,
      );

      _scanSubscription = FlutterBluePlus.scanResults.listen((results) {
        _discoveredDevices = results
            .where((r) => r.device.platformName.isNotEmpty)
            .map((r) => MeshtasticDevice(
                  device: r.device,
                  name: r.device.platformName,
                  rssi: r.rssi,
                ))
            .toList();
        notifyListeners();
      });

      // Auto-stop after timeout
      Future.delayed(timeout, () {
        if (_isScanning) stopScan();
      });
    } catch (e) {
      _error = 'Scan failed: $e';
      _isScanning = false;
      notifyListeners();
    }
  }

  /// Stop BLE scanning.
  void stopScan() {
    FlutterBluePlus.stopScan();
    _scanSubscription?.cancel();
    _scanSubscription = null;
    _isScanning = false;
    notifyListeners();
  }

  /// Connect to a discovered Meshtastic device.
  Future<void> connectToDevice(MeshtasticDevice meshDevice) async {
    if (_isConnecting) return;

    _isConnecting = true;
    _error = null;
    _statusMessage = 'Connecting to ${meshDevice.name}...';
    notifyListeners();

    try {
      await meshDevice.device.connect(timeout: const Duration(seconds: 15));
      _connectedDevice = meshDevice;
      _statusMessage = 'Connected to ${meshDevice.name}';
    } catch (e) {
      _error = 'Connection failed: $e';
      _statusMessage = null;
    }
    _isConnecting = false;
    notifyListeners();
  }

  /// Disconnect from the current device.
  Future<void> disconnect() async {
    if (_connectedDevice != null) {
      await _connectedDevice!.device.disconnect();
      _connectedDevice = null;
      _statusMessage = null;
      notifyListeners();
    }
  }

  /// Fetch mesh config from the backend and push it to the connected device.
  Future<void> pushConfiguration() async {
    if (_connectedDevice == null) {
      _error = 'No device connected';
      notifyListeners();
      return;
    }

    _isPushingConfig = true;
    _error = null;
    _statusMessage = 'Fetching mesh configuration...';
    notifyListeners();

    try {
      // 1. Fetch config from backend
      final json = await _api.get(ApiConfig.meshConfigPath);
      final config = MeshConfig.fromJson(json);

      _statusMessage = 'Discovering services...';
      notifyListeners();

      // 2. Discover BLE services
      final services = await _connectedDevice!.device.discoverServices();
      final meshService = services.firstWhere(
        (s) => s.uuid.toString().toLowerCase() == _meshtasticServiceUuid,
        orElse: () => throw Exception('Meshtastic service not found on device'),
      );

      final toRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == _toRadioCharUuid,
        orElse: () => throw Exception('toRadio characteristic not found'),
      );

      // 3. Build a config payload to push
      //    This is a simplified JSON config push. A full implementation would
      //    use Meshtastic protobuf AdminMessage framing.
      final configPayload = {
        'type': 'aervyx_config',
        'mqtt_host': config.mqttHost,
        'mqtt_port': config.mqttPort,
        'topic_prefix': config.topicPrefix,
        if (config.channelPsk != null) 'channel_psk': config.channelPsk,
      };

      _statusMessage = 'Pushing configuration...';
      notifyListeners();

      final bytes = Uint8List.fromList(utf8.encode(jsonEncode(configPayload)));
      await toRadio.write(bytes, withoutResponse: false);

      _statusMessage = 'Configuration pushed successfully';
    } catch (e) {
      _error = 'Config push failed: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  @override
  void dispose() {
    stopScan();
    disconnect();
    super.dispose();
  }
}
