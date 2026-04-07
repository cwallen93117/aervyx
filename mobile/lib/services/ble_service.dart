import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';

import '../config/api_config.dart';
import '../models/meshtastic_protobufs.dart';
import 'api_service.dart';

/// Meshtastic BLE service UUID.
const String _meshServiceUuid = '6ba1b218-15a8-461f-9fa8-5dcae273eafd';

/// Meshtastic toRadio characteristic — phone writes to device.
const String _toRadioCharUuid = 'f75c76d2-129e-4dad-a1dd-7866124401e7';

/// Meshtastic fromRadio characteristic — phone reads from device.
const String _fromRadioCharUuid = '2c55e69e-4993-11ed-b878-0242ac120002';

/// Meshtastic fromNum characteristic — notify on new data.
const String _fromNumCharUuid = 'ed9da18c-a800-4f66-a670-aa7547e34453';

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

/// BLE service for scanning, connecting, reading config from, and writing
/// config to Meshtastic radios using the protobuf BLE API.
class BleService extends ChangeNotifier {
  final ApiService _api;

  // ── Scan state ──
  List<MeshtasticDevice> _discoveredDevices = [];
  MeshtasticDevice? _connectedDevice;
  bool _isScanning = false;
  bool _isConnecting = false;
  String? _connectingDeviceId; // remoteId of the device being connected
  bool _isPushingConfig = false;
  String? _error;
  String? _statusMessage;
  StreamSubscription<List<ScanResult>>? _scanSubscription;

  // ── BLE characteristics (cached after connect) ──
  BluetoothCharacteristic? _toRadio;
  BluetoothCharacteristic? _fromRadio;
  BluetoothCharacteristic? _fromNum;

  // ── Device state (populated by config dump) ──
  MeshtasticDeviceState _deviceState = MeshtasticDeviceState();
  bool _configLoaded = false;

  // ── Phone GPS sharing ──
  StreamSubscription<Position>? _phoneGpsSubscription;
  Timer? _phoneGpsTimer;
  Position? _lastPhonePosition;

  // ── Auto-reconnect ──
  bool _userDisconnected = false;
  bool _isReconnecting = false;
  int _reconnectAttempts = 0;
  static const int _maxReconnectAttempts = 10;
  Timer? _reconnectTimer;
  StreamSubscription<BluetoothConnectionState>? _connectionStateSubscription;

  // ── Mesh position relay ──
  StreamSubscription<List<int>>? _fromNumSubscription;
  Timer? _meshPollTimer;

  // ── SOS ──
  String _sosMessage = 'SOS — Pilot needs immediate assistance';
  bool _isSendingSos = false;

  // ── Getters ──
  List<MeshtasticDevice> get discoveredDevices => _discoveredDevices;
  MeshtasticDevice? get connectedDevice => _connectedDevice;
  bool get isScanning => _isScanning;
  bool get isConnecting => _isConnecting;
  String? get connectingDeviceId => _connectingDeviceId;
  bool get isPushingConfig => _isPushingConfig;
  String? get error => _error;
  String? get statusMessage => _statusMessage;
  bool get isConnected => _connectedDevice != null;
  MeshtasticDeviceState get deviceState => _deviceState;
  bool get configLoaded => _configLoaded;
  String get sosMessage => _sosMessage;
  bool get isSendingSos => _isSendingSos;
  bool get reconnecting => _isReconnecting;

  /// Display name — prefer the Meshtastic long name, fall back to BLE name.
  String get deviceDisplayName {
    if (_deviceState.longName.isNotEmpty) return _deviceState.longName;
    return _connectedDevice?.name ?? '';
  }

  // ── Cached platform MQTT config (fetched from server) ──
  String? _platformMqttHost;
  int _platformMqttPort = 1883;
  String _platformMqttTopicPrefix = 'msh';
  String? _platformMqttPsk;

  BleService(this._api);

  // ═══════════════════════════════════════════════════════════════════════════
  // Platform config sync — called once per app open when authenticated
  // ═══════════════════════════════════════════════════════════════════════════

  /// Fetch MQTT config and device profiles from the backend.
  /// Silently uses cached/default values if the server is unreachable.
  Future<void> syncPlatformConfig() async {
    // Load from local cache first (instant, works offline)
    await _loadCachedConfig();

    // Then try to refresh from server
    try {
      // Fetch MQTT config
      final meshConfig = await _api.get(ApiConfig.meshConfigPath);
      _platformMqttHost = meshConfig['mqtt_host'] as String?;
      _platformMqttPort = meshConfig['mqtt_port'] as int? ?? 1883;
      _platformMqttTopicPrefix = meshConfig['topic_prefix'] as String? ?? 'msh';
      _platformMqttPsk = meshConfig['channel_psk'] as String?;

      // Fetch profiles
      final profilesResp = await _api.get(ApiConfig.meshProfilesPath);
      final profiles = profilesResp['profiles'];
      if (profiles is Map<String, dynamic>) {
        ProfileConfig.updatePresetsFromServer(profiles);
      }

      // Cache for offline use
      await _saveCachedConfig(meshConfig, profiles);
      notifyListeners();
    } catch (_) {
      // Server unreachable — use cached/default values silently
    }
  }

  Future<File> get _cacheFile async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/platform_config.json');
  }

  Future<void> _loadCachedConfig() async {
    try {
      final file = await _cacheFile;
      if (await file.exists()) {
        final data = jsonDecode(await file.readAsString());
        if (data is Map<String, dynamic>) {
          final mqtt = data['mqtt'];
          if (mqtt is Map<String, dynamic>) {
            _platformMqttHost = mqtt['mqtt_host'] as String?;
            _platformMqttPort = mqtt['mqtt_port'] as int? ?? 1883;
            _platformMqttTopicPrefix = mqtt['topic_prefix'] as String? ?? 'msh';
            _platformMqttPsk = mqtt['channel_psk'] as String?;
          }
          final profiles = data['profiles'];
          if (profiles is Map<String, dynamic>) {
            ProfileConfig.updatePresetsFromServer(profiles);
          }
        }
      }
    } catch (_) {
      // Cache read failed — use defaults
    }
  }

  Future<void> _saveCachedConfig(
      Map<String, dynamic> mqtt, dynamic profiles) async {
    try {
      final file = await _cacheFile;
      await file.writeAsString(jsonEncode({
        'mqtt': mqtt,
        'profiles': profiles,
        'cached_at': DateTime.now().toUtc().toIso8601String(),
      }));
    } catch (_) {
      // Cache write failed — non-critical
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Mesh device auto-registration
  // ═══════════════════════════════════════════════════════════════════════════

  /// Register the connected device's node ID against the logged-in user.
  /// Called automatically after BLE connection + config dump completes.
  /// If the user switches devices, the new ID overwrites the old one.
  Future<void> _registerMeshDevice() async {
    if (_deviceState.myNodeNum == 0) return;
    final deviceId =
        '!${_deviceState.myNodeNum.toRadixString(16).padLeft(8, '0')}';
    try {
      await _api.put(
        ApiConfig.meshDeviceRegisterPath,
        body: {'mesh_device_id': deviceId},
      );
      debugPrint('Registered mesh device $deviceId');
    } catch (e) {
      // Non-critical — device will still work, just won't resolve in MQTT
      debugPrint('Failed to register mesh device: $e');
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // SOS
  // ═══════════════════════════════════════════════════════════════════════════

  void setSosMessage(String message) {
    _sosMessage = message;
    notifyListeners();
  }

  Future<bool> sendSos() async {
    _isSendingSos = true;
    _error = null;
    notifyListeners();

    final payload = {
      'type': 'sos',
      'message': _sosMessage,
      'timestamp': DateTime.now().toUtc().toIso8601String(),
    };

    bool meshSent = false;
    bool cellularSent = false;
    final errors = <String>[];

    // Mesh (BLE)
    if (_toRadio != null) {
      try {
        final bytes = Uint8List.fromList(utf8.encode(jsonEncode(payload)));
        await _toRadio!.write(bytes, withoutResponse: false);
        meshSent = true;
      } catch (e) {
        errors.add('Mesh: $e');
      }
    }

    // Cellular (HTTP)
    try {
      await _api.post(ApiConfig.sosPath, body: payload);
      cellularSent = true;
    } catch (e) {
      errors.add('Cellular: $e');
    }

    if (meshSent || cellularSent) {
      final channels = <String>[
        if (meshSent) 'mesh',
        if (cellularSent) 'cellular',
      ];
      _statusMessage = 'SOS sent via ${channels.join(' + ')}!';
    } else {
      _error = 'SOS failed on all channels: ${errors.join('; ')}';
    }

    _isSendingSos = false;
    notifyListeners();
    return meshSent || cellularSent;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Scanning
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> startScan(
      {Duration timeout = const Duration(seconds: 10)}) async {
    if (_isScanning) return;

    _isScanning = true;
    _discoveredDevices = [];
    _error = null;
    notifyListeners();

    try {
      // Ensure Bluetooth is on
      if (await FlutterBluePlus.adapterState.first !=
          BluetoothAdapterState.on) {
        await FlutterBluePlus.turnOn();
      }

      // Request location permission (required for BLE scanning on Android)
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          _error = 'Location permission required for Bluetooth scanning';
          _isScanning = false;
          notifyListeners();
          return;
        }
      }
      if (permission == LocationPermission.deniedForever) {
        _error =
            'Location permission permanently denied. Enable in Settings.';
        _isScanning = false;
        notifyListeners();
        return;
      }

      await FlutterBluePlus.startScan(
        withServices: [Guid(_meshServiceUuid)],
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

      Future.delayed(timeout, () {
        if (_isScanning) stopScan();
      });
    } catch (e) {
      _error = 'Scan failed: $e';
      _isScanning = false;
      notifyListeners();
    }
  }

  void stopScan() {
    FlutterBluePlus.stopScan();
    _scanSubscription?.cancel();
    _scanSubscription = null;
    _isScanning = false;
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Connect / Disconnect
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> connectToDevice(MeshtasticDevice meshDevice) async {
    if (_isConnecting) return;

    _isConnecting = true;
    _connectingDeviceId = meshDevice.device.remoteId.toString();
    _userDisconnected = false;
    _reconnectAttempts = 0;
    _isReconnecting = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _error = null;
    _statusMessage = 'Connecting to ${meshDevice.name}...';
    _configLoaded = false;
    notifyListeners();

    try {
      await meshDevice.device.connect(timeout: const Duration(seconds: 15));
      _connectedDevice = meshDevice;

      // Listen for unexpected disconnects
      _connectionStateSubscription?.cancel();
      _connectionStateSubscription = meshDevice.device.connectionState.listen(
        (state) {
          if (state == BluetoothConnectionState.disconnected) {
            _onUnexpectedDisconnect();
          }
        },
      );

      // Discover BLE services and cache characteristics
      _statusMessage = 'Discovering services...';
      notifyListeners();

      final services = await meshDevice.device.discoverServices();
      final meshService = services.firstWhere(
        (s) => s.uuid.toString().toLowerCase() == _meshServiceUuid,
        orElse: () => throw Exception('Meshtastic service not found'),
      );

      _toRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == _toRadioCharUuid,
        orElse: () => throw Exception('toRadio not found'),
      );
      _fromRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == _fromRadioCharUuid,
        orElse: () => throw Exception('fromRadio not found'),
      );
      try {
        _fromNum = meshService.characteristics.firstWhere(
          (c) => c.uuid.toString().toLowerCase() == _fromNumCharUuid,
        );
      } catch (_) {
        _fromNum = null; // Not all devices expose fromNum
      }

      // Read the full config dump from the device
      _statusMessage = 'Reading device configuration...';
      notifyListeners();
      await _readDeviceConfig();

      _statusMessage = 'Connected to ${meshDevice.name}';
      _configLoaded = true;

      // Auto-register this device's node ID against the logged-in user
      _registerMeshDevice();

      // Start phone GPS sharing and mesh position relay
      _startPhoneGpsSharing();
      _startMeshPositionRelay();
    } catch (e) {
      _error = 'Connection failed: $e';
      _statusMessage = null;
      _connectedDevice = null;
      _toRadio = null;
      _fromRadio = null;
      _fromNum = null;
      _connectionStateSubscription?.cancel();
      _connectionStateSubscription = null;
    }

    _isConnecting = false;
    _connectingDeviceId = null;
    notifyListeners();
  }

  Future<void> disconnect() async {
    _userDisconnected = true;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _isReconnecting = false;
    _connectionStateSubscription?.cancel();
    _connectionStateSubscription = null;
    _stopPhoneGpsSharing();
    _stopMeshPositionRelay();
    if (_connectedDevice != null) {
      try {
        await _connectedDevice!.device.disconnect();
      } catch (_) {}
      _connectedDevice = null;
      _toRadio = null;
      _fromRadio = null;
      _fromNum = null;
      _configLoaded = false;
      _deviceState = MeshtasticDeviceState();
      _statusMessage = null;
      notifyListeners();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Auto-reconnect on unexpected disconnect
  // ═══════════════════════════════════════════════════════════════════════════

  void _onUnexpectedDisconnect() {
    // Guard against duplicate disconnect events while already reconnecting
    if (_isReconnecting) return;

    // Clean up connection state
    _stopPhoneGpsSharing();
    _stopMeshPositionRelay();
    _toRadio = null;
    _fromRadio = null;
    _fromNum = null;
    _configLoaded = false;
    _deviceState = MeshtasticDeviceState();

    if (_userDisconnected || _isConnecting) return;

    final device = _connectedDevice;
    _connectedDevice = null;

    if (device != null &&
        _reconnectAttempts < _maxReconnectAttempts) {
      _isReconnecting = true;
      _statusMessage = 'Connection lost. Reconnecting...';
      notifyListeners();
      _scheduleReconnect(device);
    } else {
      _isReconnecting = false;
      _error = _reconnectAttempts >= _maxReconnectAttempts
          ? 'Reconnection failed after $_maxReconnectAttempts attempts'
          : 'Device disconnected';
      _statusMessage = null;
      notifyListeners();
    }
  }

  void _scheduleReconnect(MeshtasticDevice device) {
    final delaySecs = min(30, 2 * pow(2, _reconnectAttempts)).toInt();
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(Duration(seconds: delaySecs), () {
      _attemptReconnect(device);
    });
  }

  Future<void> _attemptReconnect(MeshtasticDevice device) async {
    if (_userDisconnected) {
      _isReconnecting = false;
      notifyListeners();
      return;
    }

    _reconnectAttempts++;
    _statusMessage =
        'Reconnecting (attempt $_reconnectAttempts/$_maxReconnectAttempts)...';
    notifyListeners();

    try {
      await device.device.connect(timeout: const Duration(seconds: 15));
      _connectedDevice = device;

      // Re-subscribe to disconnect events
      _connectionStateSubscription?.cancel();
      _connectionStateSubscription = device.device.connectionState.listen(
        (state) {
          if (state == BluetoothConnectionState.disconnected) {
            _onUnexpectedDisconnect();
          }
        },
      );

      // Rediscover services
      final services = await device.device.discoverServices();
      final meshService = services.firstWhere(
        (s) => s.uuid.toString().toLowerCase() == _meshServiceUuid,
        orElse: () => throw Exception('Meshtastic service not found'),
      );

      _toRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == _toRadioCharUuid,
        orElse: () => throw Exception('toRadio not found'),
      );
      _fromRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == _fromRadioCharUuid,
        orElse: () => throw Exception('fromRadio not found'),
      );
      try {
        _fromNum = meshService.characteristics.firstWhere(
          (c) => c.uuid.toString().toLowerCase() == _fromNumCharUuid,
        );
      } catch (_) {
        _fromNum = null;
      }

      // Re-read config
      await _readDeviceConfig();
      _configLoaded = true;

      // Restart GPS sharing and mesh relay
      _startPhoneGpsSharing();
      _startMeshPositionRelay();

      _isReconnecting = false;
      _reconnectAttempts = 0;
      _error = null;
      _statusMessage = 'Reconnected to ${device.name}';
      notifyListeners();
    } catch (e) {
      _connectedDevice = null;
      if (_reconnectAttempts < _maxReconnectAttempts && !_userDisconnected) {
        _scheduleReconnect(device);
      } else {
        _isReconnecting = false;
        _error = 'Reconnection failed after $_reconnectAttempts attempts';
        _statusMessage = null;
        notifyListeners();
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Read device config via protobuf handshake
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _readDeviceConfig() async {
    if (_toRadio == null || _fromRadio == null) return;

    _deviceState = MeshtasticDeviceState();

    // Send want_config_id with a random nonce
    final configId = Random().nextInt(0xFFFFFF) + 1;
    final wantConfig = buildWantConfigMessage(configId);
    await _toRadio!.write(wantConfig, withoutResponse: false);

    // Read all FromRadio responses until config_complete_id matches.
    // Use a total timeout rather than a fixed empty-read count so that
    // slower devices still have time to deliver the full config dump.
    final deadline = DateTime.now().add(const Duration(seconds: 10));

    while (DateTime.now().isBefore(deadline)) {
      // Delay between reads to give the device time to queue responses
      await Future.delayed(const Duration(milliseconds: 100));

      List<int> data;
      try {
        data = await _fromRadio!.read();
      } catch (_) {
        break;
      }

      if (data.isEmpty) {
        // No data yet — keep polling until the deadline
        continue;
      }

      _parseFromRadio(Uint8List.fromList(data));

      // Check if we got config_complete_id
      // (parsed in _parseFromRadio — sets _configLoaded)
      if (_configLoaded) break;
    }
  }

  void _parseFromRadio(Uint8List data) {
    try {
      final reader = ProtoReader(data);
      while (reader.hasMore) {
        final (field, wireType) = reader.readTag();
        switch (field) {
          case 1: // id (uint32) — FromRadio packet id
            reader.readVarint();
            break;
          case 2: // packet (MeshPacket) — skip
            reader.skip(wireType);
            break;
          case 3: // my_info (MyNodeInfo)
            final sub = reader.readMessageReader();
            _parseMyNodeInfo(sub);
            break;
          case 4: // node_info (NodeInfo) — parse for User long/short name
            final sub = reader.readMessageReader();
            _parseNodeInfo(sub);
            break;
          case 5: // config (Config)
            final sub = reader.readMessageReader();
            _parseConfig(sub);
            break;
          case 6: // log_record
            reader.skip(wireType);
            break;
          case 7: // config_complete_id
            reader.readVarint();
            _configLoaded = true;
            break;
          case 8: // rebooted
            reader.skip(wireType);
            break;
          case 9: // moduleConfig
            final sub = reader.readMessageReader();
            _parseModuleConfig(sub);
            break;
          case 10: // channel
            final sub = reader.readMessageReader();
            _parseChannel(sub);
            break;
          case 13: // metadata (DeviceMetadata)
            final sub = reader.readMessageReader();
            _parseDeviceMetadata(sub);
            break;
          default:
            reader.skip(wireType);
        }
      }
    } catch (_) {
      // Malformed protobuf — skip
    }
  }

  void _parseMyNodeInfo(ProtoReader reader) {
    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // my_node_num
          _deviceState.myNodeNum = reader.readVarint();
          break;
        default:
          reader.skip(wireType);
      }
    }
  }

  void _parseNodeInfo(ProtoReader reader) {
    int? nodeNum;
    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // num
          nodeNum = reader.readVarint();
          break;
        case 2: // user (User)
          final userReader = reader.readMessageReader();
          // Only parse our own node's User info
          if (nodeNum == _deviceState.myNodeNum || _deviceState.myNodeNum == 0) {
            _parseUser(userReader);
          }
          break;
        default:
          reader.skip(wireType);
      }
    }
  }

  void _parseUser(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 2: // long_name
          _deviceState.longName = r.readString();
          break;
        case 3: // short_name
          _deviceState.shortName = r.readString();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseConfig(ProtoReader reader) {
    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // device
          _parseDeviceConfig(reader.readMessageReader());
          break;
        case 2: // position
          _parsePositionConfig(reader.readMessageReader());
          break;
        case 3: // power
          _parsePowerConfig(reader.readMessageReader());
          break;
        case 4: // network
          _parseNetworkConfig(reader.readMessageReader());
          break;
        case 5: // display
          _parseDisplayConfig(reader.readMessageReader());
          break;
        case 6: // lora
          _parseLoraConfig(reader.readMessageReader());
          break;
        case 7: // bluetooth
          _parseBluetoothConfig(reader.readMessageReader());
          break;
        default:
          reader.skip(wireType);
      }
    }
  }

  void _parseDeviceConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.role = DeviceRole.fromValue(r.readVarint());
          break;
        case 6:
          _deviceState.rebroadcastMode =
              RebroadcastMode.fromValue(r.readVarint());
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parsePositionConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1: // position_broadcast_secs
          _deviceState.positionBroadcastSecs = r.readVarint();
          break;
        case 2: // position_broadcast_smart_enabled
          _deviceState.smartPositionEnabled = r.readBool();
          break;
        case 7: // position_flags
          _deviceState.positionFlags = r.readVarint();
          break;
        case 10: // broadcast_smart_minimum_distance
          _deviceState.smartMinDistance = r.readVarint();
          break;
        case 11: // broadcast_smart_minimum_interval_secs
          _deviceState.smartMinInterval = r.readVarint();
          break;
        case 13: // gps_mode
          _deviceState.gpsMode = GpsMode.fromValue(r.readVarint());
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parsePowerConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.isPowerSaving = r.readBool();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseNetworkConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.wifiEnabled = r.readBool();
          break;
        case 3:
          _deviceState.wifiSsid = r.readString();
          break;
        case 4:
          _deviceState.wifiPsk = r.readString();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseDisplayConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.screenOnSecs = r.readVarint();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseLoraConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 2: // modem_preset
          _deviceState.modemPreset = ModemPreset.fromValue(r.readVarint());
          break;
        case 7: // region
          _deviceState.region = RegionCode.fromValue(r.readVarint());
          break;
        case 8: // hop_limit
          _deviceState.hopLimit = r.readVarint();
          break;
        case 9: // tx_enabled
          _deviceState.txEnabled = r.readBool();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseBluetoothConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.bluetoothEnabled = r.readBool();
          break;
        case 2:
          _deviceState.blePairingMode =
              BlePairingMode.fromValue(r.readVarint());
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseModuleConfig(ProtoReader reader) {
    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // mqtt
          _parseMqttConfig(reader.readMessageReader());
          break;
        case 4: // store_forward
          _parseStoreForwardConfig(reader.readMessageReader());
          break;
        case 6: // telemetry
          _parseTelemetryConfig(reader.readMessageReader());
          break;
        case 10: // neighbor_info
          _parseNeighborInfoConfig(reader.readMessageReader());
          break;
        default:
          reader.skip(wireType);
      }
    }
  }

  void _parseMqttConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.mqttEnabled = r.readBool();
          break;
        case 2:
          _deviceState.mqttAddress = r.readString();
          break;
        case 3:
          _deviceState.mqttUsername = r.readString();
          break;
        case 4:
          _deviceState.mqttPassword = r.readString();
          break;
        case 5:
          _deviceState.mqttEncryptionEnabled = r.readBool();
          break;
        case 7:
          _deviceState.mqttTlsEnabled = r.readBool();
          break;
        case 8:
          _deviceState.mqttRootTopic = r.readString();
          break;
        case 9:
          _deviceState.mqttProxyToClient = r.readBool();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseTelemetryConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.telemetryDeviceInterval = r.readVarint();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseStoreForwardConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.storeForwardEnabled = r.readBool();
          break;
        case 6: // is_server (StoreForwardConfig field 6)
          _deviceState.storeForwardIsServer = r.readBool();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseNeighborInfoConfig(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.neighborInfoEnabled = r.readBool();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  void _parseChannel(ProtoReader reader) {
    int? index;
    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // index
          index = reader.readVarint();
          break;
        case 2: // settings
          if (index == 0) {
            // Primary channel
            final sub = reader.readMessageReader();
            while (sub.hasMore) {
              final (sf, swt) = sub.readTag();
              switch (sf) {
                case 3: // name (ChannelSettings field 3)
                  _deviceState.channelName = sub.readString();
                  break;
                case 5: // uplink_enabled
                  _deviceState.channelUplinkEnabled = sub.readBool();
                  break;
                case 6: // downlink_enabled
                  _deviceState.channelDownlinkEnabled = sub.readBool();
                  break;
                default:
                  sub.skip(swt);
              }
            }
          } else {
            reader.skip(wireType);
          }
          break;
        default:
          reader.skip(wireType);
      }
    }
  }

  void _parseDeviceMetadata(ProtoReader r) {
    while (r.hasMore) {
      final (f, wt) = r.readTag();
      switch (f) {
        case 1:
          _deviceState.firmwareVersion = r.readString();
          break;
        default:
          r.skip(wt);
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Write config to device
  // ═══════════════════════════════════════════════════════════════════════════

  /// Write a single admin message to the connected device.
  Future<void> _writeAdmin(Uint8List adminPayload) async {
    if (_toRadio == null) throw Exception('Not connected');

    final meshPacket = buildAdminPacket(
      to: _deviceState.myNodeNum,
      from: _deviceState.myNodeNum,
      adminPayload: adminPayload,
    );
    final toRadio = buildToRadioPacket(meshPacket);
    await _toRadio!.write(toRadio, withoutResponse: false);

    // Small delay between writes to avoid overwhelming the device
    await Future.delayed(const Duration(milliseconds: 100));
  }

  /// Apply a full profile preset to the connected device.
  Future<void> applyProfile(MeshtasticProfile profile) async {
    if (_toRadio == null) {
      _error = 'No device connected';
      notifyListeners();
      return;
    }

    final config = ProfileConfig.presets[profile]!;
    _isPushingConfig = true;
    _error = null;
    _statusMessage = 'Applying ${profile.label} profile...';
    notifyListeners();

    try {
      // Begin batch edit
      await _writeAdmin(buildBeginEditSettings());

      // Device config (role + rebroadcast)
      _statusMessage = 'Setting device role...';
      notifyListeners();
      await _writeAdmin(buildSetDeviceConfig(
        role: config.role,
        rebroadcastMode: config.rebroadcastMode,
      ));

      // Position config
      _statusMessage = 'Setting position config...';
      notifyListeners();
      await _writeAdmin(buildSetPositionConfig(
        positionBroadcastSecs: config.positionBroadcastSecs,
        smartEnabled: config.smartPositionEnabled,
        smartMinDistance: config.smartMinDistance,
        smartMinInterval: config.smartMinInterval,
        gpsMode: config.gpsMode,
        positionFlags: config.positionFlags,
      ));

      // LoRa config
      _statusMessage = 'Setting LoRa radio...';
      notifyListeners();
      await _writeAdmin(buildSetLoraConfig(
        modemPreset: config.modemPreset,
        region: _deviceState.region, // Keep current region
        hopLimit: config.hopLimit,
      ));

      // Power config
      await _writeAdmin(buildSetPowerConfig(
        isPowerSaving: config.powerSaving,
      ));

      // Display config
      await _writeAdmin(buildSetDisplayConfig(
        screenOnSecs: config.displayTimeoutSecs,
      ));

      // Network/Wi-Fi
      await _writeAdmin(buildSetNetworkConfig(
        wifiEnabled: config.wifiEnabled,
      ));

      // MQTT — always on, use platform config from admin settings
      _statusMessage = 'Setting MQTT...';
      notifyListeners();
      await _writeAdmin(buildSetMqttConfig(
        address: _platformMqttHost ?? 'mqtt.meshtastic.org',
        rootTopic: _platformMqttTopicPrefix,
        encryptionEnabled: _deviceState.mqttEncryptionEnabled,
        proxyToClientEnabled: config.bluetoothEnabled, // Proxy when BLE on
      ));

      // Telemetry
      await _writeAdmin(buildSetTelemetryConfig(
        deviceUpdateInterval: config.telemetryIntervalSecs,
      ));

      // Neighbor info — on for all profiles
      await _writeAdmin(buildSetNeighborInfoConfig(enabled: true));

      // Store & forward — on for repeaters as server, on for others as client
      await _writeAdmin(buildSetStoreForwardConfig(
        enabled: true,
        isServer: profile == MeshtasticProfile.repeater,
      ));

      // Channel uplink — always on
      await _writeAdmin(buildSetChannel(
        index: 0,
        role: 1, // PRIMARY
        uplinkEnabled: true,
        downlinkEnabled: true,
      ));

      // Bluetooth config — kept last before commit as defense-in-depth.
      // All profiles now keep BLE on so the device remains reachable.
      await _writeAdmin(buildSetBluetoothConfig(
        enabled: config.bluetoothEnabled,
      ));

      // Commit batch edit (device reboots)
      _statusMessage = 'Committing settings (device will reboot)...';
      notifyListeners();
      await _writeAdmin(buildCommitEditSettings());

      // Update local state to match
      _deviceState.role = config.role;
      _deviceState.rebroadcastMode = config.rebroadcastMode;
      _deviceState.gpsMode = config.gpsMode;
      _deviceState.positionBroadcastSecs = config.positionBroadcastSecs;
      _deviceState.smartPositionEnabled = config.smartPositionEnabled;
      _deviceState.smartMinDistance = config.smartMinDistance;
      _deviceState.smartMinInterval = config.smartMinInterval;
      _deviceState.modemPreset = config.modemPreset;
      _deviceState.hopLimit = config.hopLimit;
      _deviceState.isPowerSaving = config.powerSaving;
      _deviceState.bluetoothEnabled = config.bluetoothEnabled;
      _deviceState.wifiEnabled = config.wifiEnabled;
      _deviceState.positionFlags = config.positionFlags;
      _deviceState.screenOnSecs = config.displayTimeoutSecs;
      _deviceState.telemetryDeviceInterval = config.telemetryIntervalSecs;

      _statusMessage = '${profile.label} profile applied. Device rebooting...';
    } catch (e) {
      _error = 'Profile apply failed: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Individual config writes
  // ═══════════════════════════════════════════════════════════════════════════

  /// Set device long name and short name.
  Future<void> setDeviceName({
    required String longName,
    required String shortName,
  }) async {
    _isPushingConfig = true;
    _statusMessage = 'Setting device name...';
    _error = null;
    notifyListeners();

    try {
      await _writeAdmin(buildSetOwner(
        longName: longName,
        shortName: shortName,
      ));
      _deviceState.longName = longName;
      _deviceState.shortName = shortName;
      _statusMessage = 'Device name updated';
    } catch (e) {
      _error = 'Failed to set name: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  /// Configure Wi-Fi on the device.
  Future<void> setWifi({
    required bool enabled,
    String? ssid,
    String? password,
  }) async {
    _isPushingConfig = true;
    _statusMessage = enabled ? 'Configuring Wi-Fi...' : 'Disabling Wi-Fi...';
    _error = null;
    notifyListeners();

    try {
      await _writeAdmin(buildSetNetworkConfig(
        wifiEnabled: enabled,
        wifiSsid: ssid,
        wifiPsk: password,
      ));
      _deviceState.wifiEnabled = enabled;
      if (ssid != null) _deviceState.wifiSsid = ssid;
      _statusMessage = enabled ? 'Wi-Fi configured' : 'Wi-Fi disabled';
    } catch (e) {
      _error = 'Wi-Fi config failed: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  /// Set LoRa region.
  Future<void> setLoraRegion(RegionCode region) async {
    _isPushingConfig = true;
    _statusMessage = 'Setting region...';
    _error = null;
    notifyListeners();

    try {
      await _writeAdmin(buildSetLoraConfig(
        modemPreset: _deviceState.modemPreset,
        region: region,
        hopLimit: _deviceState.hopLimit,
      ));
      _deviceState.region = region;
      _statusMessage = 'Region set to ${region.label}';
    } catch (e) {
      _error = 'Failed to set region: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  /// Set MQTT server configuration.
  Future<void> setMqttConfig({
    required String address,
    String? username,
    String? password,
    required String rootTopic,
    bool encryptionEnabled = true,
    bool tlsEnabled = false,
  }) async {
    _isPushingConfig = true;
    _statusMessage = 'Configuring MQTT...';
    _error = null;
    notifyListeners();

    try {
      await _writeAdmin(buildSetMqttConfig(
        address: address,
        username: username,
        password: password,
        rootTopic: rootTopic,
        encryptionEnabled: encryptionEnabled,
        tlsEnabled: tlsEnabled,
        proxyToClientEnabled: _deviceState.bluetoothEnabled,
      ));
      _deviceState.mqttAddress = address;
      if (username != null) _deviceState.mqttUsername = username;
      _deviceState.mqttRootTopic = rootTopic;
      _deviceState.mqttEncryptionEnabled = encryptionEnabled;
      _deviceState.mqttTlsEnabled = tlsEnabled;
      _statusMessage = 'MQTT configured';
    } catch (e) {
      _error = 'MQTT config failed: $e';
      _statusMessage = null;
    }

    _isPushingConfig = false;
    notifyListeners();
  }

  /// Reboot the device.
  Future<void> rebootDevice({int seconds = 5}) async {
    _statusMessage = 'Rebooting device in $seconds seconds...';
    notifyListeners();
    try {
      await _writeAdmin(buildReboot(seconds: seconds));
    } catch (_) {}
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Phone GPS sharing — always on when connected
  // ═══════════════════════════════════════════════════════════════════════════

  void _startPhoneGpsSharing() {
    _stopPhoneGpsSharing();

    const settings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 10,
    );

    _phoneGpsSubscription =
        Geolocator.getPositionStream(locationSettings: settings)
            .listen(_onPhoneGpsUpdate);

    // Also send position every 30 seconds even if stationary
    _phoneGpsTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _sendPhonePosition(),
    );
  }

  void _stopPhoneGpsSharing() {
    _phoneGpsSubscription?.cancel();
    _phoneGpsSubscription = null;
    _phoneGpsTimer?.cancel();
    _phoneGpsTimer = null;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Mesh position relay — read positions from device and POST to backend
  // ═══════════════════════════════════════════════════════════════════════════

  void _startMeshPositionRelay() {
    _stopMeshPositionRelay();

    // Use fromNum notifications if available, otherwise poll
    if (_fromNum != null) {
      _fromNum!.setNotifyValue(true).then((_) {
        _fromNumSubscription = _fromNum!.onValueReceived.listen((_) {
          _drainFromRadio();
        });
      }).catchError((_) {
        // Fallback to polling if notifications fail
        _meshPollTimer = Timer.periodic(
          const Duration(seconds: 5),
          (_) => _drainFromRadio(),
        );
      });
    } else {
      // No fromNum — poll periodically
      _meshPollTimer = Timer.periodic(
        const Duration(seconds: 5),
        (_) => _drainFromRadio(),
      );
    }
  }

  void _stopMeshPositionRelay() {
    _fromNumSubscription?.cancel();
    _fromNumSubscription = null;
    _meshPollTimer?.cancel();
    _meshPollTimer = null;
  }

  Future<void> _drainFromRadio() async {
    if (_fromRadio == null) return;

    // Read all available packets (up to 20 per drain cycle)
    for (var i = 0; i < 20; i++) {
      List<int> data;
      try {
        data = await _fromRadio!.read();
      } catch (_) {
        break;
      }
      if (data.isEmpty) break;

      final bytes = Uint8List.fromList(data);
      // Parse for position packets and relay to backend
      _parseAndRelayMeshPacket(bytes);
    }
  }

  void _parseAndRelayMeshPacket(Uint8List data) {
    try {
      final reader = ProtoReader(data);
      while (reader.hasMore) {
        final (field, wireType) = reader.readTag();
        if (field == 2) {
          // MeshPacket
          final packetBytes = reader.readBytes();
          _handleMeshPacket(Uint8List.fromList(packetBytes));
        } else {
          reader.skip(wireType);
        }
      }
    } catch (_) {
      // Malformed protobuf — skip
    }
  }

  void _handleMeshPacket(Uint8List packetBytes) {
    try {
      final mp = ProtoReader(packetBytes);
      int? fromNode;
      Uint8List? decodedData;

      while (mp.hasMore) {
        final (field, wireType) = mp.readTag();
        switch (field) {
          case 1: // from (fixed32 — wire type 5)
            if (wireType == 5) {
              fromNode = mp.readFixed32();
            } else {
              mp.skip(wireType);
            }
            break;
          case 3: // decoded Data (length-delimited)
            decodedData = Uint8List.fromList(mp.readBytes());
            break;
          default:
            mp.skip(wireType);
        }
      }

      if (decodedData == null) return;

      // Parse the Data message
      final dataReader = ProtoReader(decodedData);
      int? portnum;
      Uint8List? payload;

      while (dataReader.hasMore) {
        final (field, wireType) = dataReader.readTag();
        switch (field) {
          case 1: // portnum (varint). POSITION_APP = 3
            portnum = dataReader.readVarint();
            break;
          case 2: // payload (bytes)
            payload = Uint8List.fromList(dataReader.readBytes());
            break;
          default:
            dataReader.skip(wireType);
        }
      }

      if (portnum != 3 || payload == null) return; // Not a position packet

      // Parse Position message
      final posReader = ProtoReader(payload);
      int? latI, lonI, alt, time, speed, heading;

      while (posReader.hasMore) {
        final (field, wireType) = posReader.readTag();
        switch (field) {
          case 1: // latitude_i (sfixed32, wire type 5)
            latI = wireType == 5 ? posReader.readSfixed32() : (posReader.skip(wireType) as dynamic);
            break;
          case 2: // longitude_i (sfixed32, wire type 5)
            lonI = wireType == 5 ? posReader.readSfixed32() : (posReader.skip(wireType) as dynamic);
            break;
          case 3: // altitude (varint)
            alt = posReader.readVarint();
            break;
          case 4: // time (varint)
            time = posReader.readVarint();
            break;
          case 8: // ground_speed (varint)
            speed = posReader.readVarint();
            break;
          case 9: // ground_track (varint)
            heading = posReader.readVarint();
            break;
          default:
            posReader.skip(wireType);
        }
      }

      if (latI == null || lonI == null) return;
      final lat = latI / 1e7;
      final lon = lonI / 1e7;
      if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return;
      if (lat == 0 && lon == 0) return; // No fix

      final deviceId = fromNode != null ? '!${fromNode.toRadixString(16).padLeft(8, '0')}' : null;

      // POST to backend
      _relayPositionToBackend(
        lat: lat,
        lon: lon,
        alt: alt?.toDouble(),
        speed: speed?.toDouble(),
        heading: heading != null ? heading / 1e5 : null,
        deviceId: deviceId,
        timestamp: time != null
            ? DateTime.fromMillisecondsSinceEpoch(time * 1000, isUtc: true)
            : null,
      );
    } catch (_) {
      // Malformed mesh packet — skip
    }
  }

  Future<void> _relayPositionToBackend({
    required double lat,
    required double lon,
    double? alt,
    double? speed,
    double? heading,
    String? deviceId,
    DateTime? timestamp,
  }) async {
    final body = <String, dynamic>{
      'lat': lat,
      'lon': lon,
      if (alt != null) 'alt': alt,
      if (speed != null) 'speed': speed,
      if (heading != null) 'heading': heading,
      if (deviceId != null) 'device_id': deviceId,
      if (timestamp != null) 'timestamp': timestamp.toIso8601String(),
      'source': 'mesh_relay',
    };

    try {
      await _api.post(ApiConfig.trackPositionPath, body: body);
    } catch (_) {
      // Backend unreachable — silently drop (not critical)
    }
  }

  void _onPhoneGpsUpdate(Position pos) {
    _lastPhonePosition = pos;
    _sendPhonePosition();
  }

  Future<void> _sendPhonePosition() async {
    if (_toRadio == null || _lastPhonePosition == null) return;
    if (_deviceState.myNodeNum == 0) return;

    final pos = _lastPhonePosition!;
    final posPacket = buildPositionPacket(
      to: _deviceState.myNodeNum,
      from: _deviceState.myNodeNum,
      lat: pos.latitude,
      lon: pos.longitude,
      alt: pos.altitude,
      time: pos.timestamp.millisecondsSinceEpoch ~/ 1000,
      groundSpeed: pos.speed.round(),
      groundTrack: pos.heading.round(),
    );

    try {
      final toRadio = buildToRadioPacket(posPacket);
      await _toRadio!.write(toRadio, withoutResponse: false);
    } catch (_) {
      // BLE write failed — device may have disconnected
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Dispose
  // ═══════════════════════════════════════════════════════════════════════════

  @override
  void dispose() {
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _connectionStateSubscription?.cancel();
    _connectionStateSubscription = null;
    _stopPhoneGpsSharing();
    _stopMeshPositionRelay();
    stopScan();
    disconnect();
    super.dispose();
  }
}
