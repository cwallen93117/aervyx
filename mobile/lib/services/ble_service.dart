import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:geolocator/geolocator.dart';
import 'package:nsd/nsd.dart' as nsd;
import 'package:path_provider/path_provider.dart';
import 'package:usb_serial/usb_serial.dart';

import '../config/api_config.dart';
import '../models/meshtastic_protobufs.dart';
import 'api_service.dart';
import 'mesh_transport.dart';
import 'mqtt_client_proxy_service.dart';
import 'persistent_runtime_service.dart';
import 'transports/ble_transport.dart';
import 'transports/tcp_transport.dart';
import 'transports/serial_transport.dart';

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

/// A Meshtastic device discovered via mDNS on the local network.
class NetworkDevice {
  final String name;
  final String host;
  final int port;

  const NetworkDevice({
    required this.name,
    required this.host,
    required this.port,
  });
}

/// BLE service for scanning, connecting, reading config from, and writing
/// config to Meshtastic radios using the protobuf BLE API.
class BleService extends ChangeNotifier {
  final ApiService _api;

  // ── Transport abstraction ──
  MeshTransport? _transport;
  ConnectionType? _connectionType;

  // ── Scan state ──
  List<MeshtasticDevice> _discoveredDevices = [];
  MeshtasticDevice? _connectedDevice; // BLE only — null for TCP/Serial
  bool _isScanning = false;
  bool _isConnecting = false;
  String? _connectingDeviceId; // remoteId of the device being connected
  bool _isPushingConfig = false;
  String? _error;
  String? _statusMessage;
  StreamSubscription<List<ScanResult>>? _scanSubscription;

  // ── USB Serial state ──
  List<UsbDevice> _discoveredUsbDevices = [];

  // ── Network (mDNS) scan state ──
  List<NetworkDevice> _discoveredNetworkDevices = [];
  bool _isNetworkScanning = false;
  nsd.Discovery? _nsdDiscovery;
  Timer? _networkScanTimer;

  // ── BLE characteristics (kept for reconnect service discovery) ──
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
  StreamSubscription<void>? _dataAvailableSubscription;
  Timer? _meshPollTimer;
  final MqttClientProxyService _mqttClientProxy = MqttClientProxyService();

  // ── Device GPS state (from own mesh position packets) ──
  double? _deviceGpsLat;
  double? _deviceGpsLon;
  double? _deviceGpsAlt;
  DateTime? _deviceGpsLastFix;
  int? _deviceGpsSats;
  double? _deviceGpsPdop; // Positional Dilution of Precision

  // ── Device battery (from telemetry packets) ──
  int? _deviceBatteryLevel; // 0-100 %
  double? _deviceVoltage; // volts

  // ── SOS ──
  String _sosMessage = 'SOS — Pilot needs immediate assistance';
  bool _isSendingSos = false;

  // ── Getters ──
  List<MeshtasticDevice> get discoveredDevices => _discoveredDevices;
  List<UsbDevice> get discoveredUsbDevices => _discoveredUsbDevices;
  List<NetworkDevice> get discoveredNetworkDevices => _discoveredNetworkDevices;
  bool get isNetworkScanning => _isNetworkScanning;
  MeshtasticDevice? get connectedDevice => _connectedDevice;
  ConnectionType? get connectionType => _connectionType;
  bool get isScanning => _isScanning;
  bool get isConnecting => _isConnecting;
  String? get connectingDeviceId => _connectingDeviceId;
  bool get isPushingConfig => _isPushingConfig;
  String? get error => _error;
  String? get statusMessage => _statusMessage;
  bool get isConnected => _transport?.isConnected == true;
  MeshtasticDeviceState get deviceState => _deviceState;
  bool get configLoaded => _configLoaded;
  String get sosMessage => _sosMessage;
  bool get isSendingSos => _isSendingSos;
  bool get reconnecting => _isReconnecting;

  /// Display name — prefer the Meshtastic long name, fall back to transport label.
  String get deviceDisplayName {
    if (_deviceState.longName.isNotEmpty) return _deviceState.longName;
    if (_connectedDevice != null) return _connectedDevice!.name;
    return _transport?.connectionLabel ?? '';
  }

  /// Connection label for display (e.g. "BLE: Meshtastic_1234", "TCP: 192.168.1.50:4403").
  String get connectionLabel => _transport?.connectionLabel ?? '';

  /// True if the device has a GPS module (not GpsMode.notPresent).
  bool get deviceHasGps =>
      _configLoaded && _deviceState.gpsMode != GpsMode.notPresent;

  /// True if the device's GPS is enabled and active.
  bool get deviceGpsEnabled =>
      _configLoaded && _deviceState.gpsMode == GpsMode.enabled;

  /// True if the device has produced at least one GPS fix.
  bool get deviceHasGpsFix => _deviceGpsLastFix != null;

  /// Device GPS last fix timestamp.
  DateTime? get deviceGpsLastFix => _deviceGpsLastFix;

  /// Device's last known position from its own GPS.
  double? get deviceGpsLat => _deviceGpsLat;
  double? get deviceGpsLon => _deviceGpsLon;
  double? get deviceGpsAlt => _deviceGpsAlt;

  /// Satellite count from device's last GPS fix.
  int? get deviceGpsSats => _deviceGpsSats;

  /// PDOP from device's last GPS fix (lower is better; <2 = excellent).
  double? get deviceGpsPdop => _deviceGpsPdop;

  /// Device battery level (0-100 %) from telemetry packets.
  int? get deviceBatteryLevel => _deviceBatteryLevel;

  /// Device voltage from telemetry packets.
  double? get deviceVoltage => _deviceVoltage;

  /// Describes the current GPS source priority state for display.
  String get gpsSourceLabel {
    if (!_configLoaded) return 'Unknown';
    if (_deviceState.gpsMode == GpsMode.notPresent)
      return 'Phone only (no device GPS)';
    if (_deviceState.gpsMode == GpsMode.disabled)
      return 'Phone only (device GPS disabled)';
    if (_deviceGpsLastFix != null) return 'Device GPS';
    return 'Phone GPS (device searching...)';
  }

  // ── Cached platform MQTT config (fetched from server) ──
  String? _platformMqttHost;
  int _platformMqttPort = 1883;
  bool _platformMqttTlsEnabled = false;
  String? _platformMqttUsername;
  String? _platformMqttPassword;
  String _platformMqttTopicPrefix = 'msh';
  String? _platformMqttPsk;

  BleService(this._api);

  String _platformMqttAddressForRadio() {
    final host = _platformMqttHost ?? '';
    final defaultPort = _platformMqttTlsEnabled ? 8883 : 1883;
    if (host.isNotEmpty &&
        _platformMqttPort > 0 &&
        _platformMqttPort != defaultPort &&
        !host.contains(':')) {
      return '$host:$_platformMqttPort';
    }
    return host;
  }

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
      _platformMqttTlsEnabled =
          meshConfig['mqtt_tls_enabled'] as bool? ?? false;
      _platformMqttUsername = meshConfig['mqtt_username'] as String?;
      _platformMqttPassword = meshConfig['mqtt_password'] as String?;
      _platformMqttTopicPrefix = meshConfig['topic_prefix'] as String? ?? 'msh';
      _platformMqttPsk = meshConfig['channel_psk'] as String?;

      // Fetch profiles
      final profilesResp = await _api.get(ApiConfig.meshProfilesPath);
      final profiles = profilesResp['profiles'];
      if (profiles is Map<String, dynamic>) {
        ProfileConfig.updatePresetsFromServer(profiles);
        // Log all preset values after server sync for debugging
        for (final entry in ProfileConfig.presets.entries) {
          final c = entry.value;
          debugPrint('syncPlatformConfig: ${entry.key.label} → '
              'role=${c.role}, broadcast=${c.positionBroadcastSecs}, '
              'gpsInterval=${c.gpsUpdateInterval}, display=${c.displayTimeoutSecs}, '
              'smartDist=${c.smartMinDistance}, smartInt=${c.smartMinInterval}');
        }
      }

      // Cache for offline use
      await _saveCachedConfig(meshConfig, profiles);
      notifyListeners();
    } catch (e) {
      // Server unreachable — use cached/default values silently
      debugPrint('syncPlatformConfig: server fetch failed: $e');
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
            _platformMqttTlsEnabled =
                mqtt['mqtt_tls_enabled'] as bool? ?? false;
            _platformMqttUsername = mqtt['mqtt_username'] as String?;
            _platformMqttPassword = mqtt['mqtt_password'] as String?;
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
    final deviceId = _currentMeshDeviceId();
    if (deviceId == null) return;
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

  /// Clear the current user's mesh_device_id (e.g. after applying a Repeater
  /// profile — infrastructure devices don't need pilot association).
  Future<void> _unregisterMeshDevice() async {
    try {
      await _api.put(
        ApiConfig.meshDeviceRegisterPath,
        body: {'mesh_device_id': null},
      );
      debugPrint('Unregistered mesh device from user');
    } catch (e) {
      debugPrint('Failed to unregister mesh device: $e');
    }
  }

  String? _currentMeshDeviceId() {
    if (_deviceState.myNodeNum == 0) return null;
    return '!${_deviceState.myNodeNum.toRadixString(16).padLeft(8, '0')}';
  }

  String _meshPurposeForCurrentState() {
    switch (_deviceState.role) {
      case DeviceRole.tracker:
      case DeviceRole.takTracker:
        return 'tracking';
      case DeviceRole.router:
      case DeviceRole.routerClient:
      case DeviceRole.repeater:
      case DeviceRole.routerLate:
      case DeviceRole.clientBase:
        return 'base_station';
      case DeviceRole.client:
      case DeviceRole.clientMute:
      case DeviceRole.clientHidden:
        return _deviceState.wifiEnabled ? 'driver_wifi' : 'driver_mesh';
      case DeviceRole.sensor:
      case DeviceRole.tak:
      case DeviceRole.lostAndFound:
        return 'relay';
    }
  }

  String _meshPurposeForProfile(MeshtasticProfile profile) {
    switch (profile) {
      case MeshtasticProfile.pilot:
        return 'tracking';
      case MeshtasticProfile.driver:
        return 'driver_mesh';
      case MeshtasticProfile.driverWifi:
        return 'driver_wifi';
      case MeshtasticProfile.repeater:
        return 'base_station';
    }
  }

  Future<void> _registerMeshDeviceInventory(String purpose) async {
    final deviceId = _currentMeshDeviceId();
    if (deviceId == null) return;
    final label = _deviceState.longName.trim().isNotEmpty
        ? _deviceState.longName.trim()
        : deviceDisplayName;
    try {
      await _api.post(
        ApiConfig.meshDevicesPath,
        body: {
          'device_id': deviceId,
          'label': label,
          'purpose': purpose,
          'is_active': true,
        },
      );
      debugPrint('Registered mesh device $deviceId as $purpose');
    } catch (e) {
      debugPrint('Failed to register mesh inventory device: $e');
    }
  }

  Future<void> _syncConnectedDeviceRegistration() async {
    final purpose = _meshPurposeForCurrentState();
    if (purpose == 'tracking') {
      await _registerMeshDevice();
    } else {
      await _registerMeshDeviceInventory(purpose);
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

    // Mesh (via transport)
    if (_transport != null) {
      try {
        final bytes = Uint8List.fromList(utf8.encode(jsonEncode(payload)));
        await _transport!.writeToRadio(bytes);
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
        _error = 'Location permission permanently denied. Enable in Settings.';
        _isScanning = false;
        notifyListeners();
        return;
      }

      await FlutterBluePlus.startScan(
        withServices: [Guid(meshServiceUuid)],
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
        (s) => s.uuid.toString().toLowerCase() == meshServiceUuid,
        orElse: () => throw Exception('Meshtastic service not found'),
      );

      _toRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == toRadioCharUuid,
        orElse: () => throw Exception('toRadio not found'),
      );
      _fromRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == fromRadioCharUuid,
        orElse: () => throw Exception('fromRadio not found'),
      );
      try {
        _fromNum = meshService.characteristics.firstWhere(
          (c) => c.uuid.toString().toLowerCase() == fromNumCharUuid,
        );
      } catch (_) {
        _fromNum = null; // Not all devices expose fromNum
      }

      // Request high connection priority for stable bulk writes.
      try {
        await meshDevice.device.requestConnectionPriority(
          connectionPriorityRequest: ConnectionPriority.high,
        );
      } catch (_) {}

      // Negotiate BLE MTU — official Meshtastic app requests 512.
      // Default Android MTU is 23 bytes (20 usable) which is too small for
      // admin packets (33–74 bytes). ESP32 typically negotiates 256-512.
      try {
        final mtu = await meshDevice.device.requestMtu(512);
        debugPrint('BLE MTU negotiated: $mtu');
      } catch (e) {
        debugPrint('BLE MTU request failed (using default): $e');
      }

      // Create BLE transport and assign
      _transport = BleTransport(
        device: meshDevice.device,
        toRadio: _toRadio!,
        fromRadio: _fromRadio!,
        fromNum: _fromNum,
      );
      _connectionType = ConnectionType.ble;
      unawaited(PersistentRuntimeService.setBleActive(true));

      // Read config, register, start relays (shared post-connect flow)
      await _postConnectSetup(meshDevice.name);
    } catch (e) {
      unawaited(PersistentRuntimeService.setBleActive(false));
      _error = 'Connection failed: $e';
      _statusMessage = null;
      _connectedDevice = null;
      _transport = null;
      _connectionType = null;
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

  /// Shared post-connect setup: read config, register device, start relays.
  Future<void> _postConnectSetup(String displayName) async {
    _statusMessage = 'Reading device configuration...';
    notifyListeners();
    await _readDeviceConfig();

    _statusMessage = 'Connected to $displayName';
    _configLoaded = true;

    // Auto-register on every connect. Tracker devices map to live pilot
    // tracking; base stations and driver devices stay in the user's device
    // inventory without becoming the live tracker.
    await _syncConnectedDeviceRegistration();

    // Start mesh position relay (always — captures all mesh traffic)
    _startMeshPositionRelay();
    _startMqttClientProxy();

    // Only share phone GPS to the device if it lacks its own GPS.
    if (_deviceState.gpsMode == GpsMode.notPresent) {
      _startPhoneGpsSharing();
      debugPrint('Device has no GPS — sharing phone GPS');
    } else {
      debugPrint(
          'Device has GPS (${_deviceState.gpsMode.label}) — not sharing phone GPS');
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // TCP (WiFi/Network) connect
  // ═══════════════════════════════════════════════════════════════════════════

  /// Connect to a Meshtastic device over TCP (WiFi).
  Future<void> connectViaTcp(String host,
      {int port = defaultMeshtasticTcpPort}) async {
    if (_isConnecting) return;

    _isConnecting = true;
    _userDisconnected = false;
    _reconnectAttempts = 0;
    _isReconnecting = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _error = null;
    _statusMessage = 'Connecting to $host:$port...';
    _configLoaded = false;
    notifyListeners();

    try {
      final tcp = TcpTransport(host: host, port: port);
      await tcp.connect();
      _transport = tcp;
      _connectionType = ConnectionType.tcp;
      _connectedDevice = null; // not BLE

      await _postConnectSetup('$host:$port');
    } catch (e) {
      _error = 'TCP connection failed: $e';
      _statusMessage = null;
      _transport = null;
      _connectionType = null;
    }

    _isConnecting = false;
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Serial (USB OTG) connect
  // ═══════════════════════════════════════════════════════════════════════════

  /// Scan for USB serial devices (Android only).
  Future<void> scanUsbDevices() async {
    try {
      _discoveredUsbDevices = await UsbSerial.listDevices();
      notifyListeners();
    } catch (e) {
      _error = 'USB scan failed: $e';
      notifyListeners();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Network (mDNS) scan
  // ═══════════════════════════════════════════════════════════════════════════

  /// Discover Meshtastic devices advertising `_meshtastic._tcp` via mDNS.
  Future<void> startNetworkScan(
      {Duration timeout = const Duration(seconds: 10)}) async {
    if (_isNetworkScanning) return;

    _isNetworkScanning = true;
    _discoveredNetworkDevices = [];
    _error = null;
    notifyListeners();

    try {
      final discovery = await nsd.startDiscovery('_meshtastic._tcp');
      _nsdDiscovery = discovery;

      discovery.addServiceListener((service, status) {
        if (status == nsd.ServiceStatus.found) {
          final rawHost = service.host;
          final rawPort = service.port;
          if (rawHost == null || rawPort == null) return;

          // Strip trailing dot that some mDNS implementations include.
          final host = rawHost.endsWith('.')
              ? rawHost.substring(0, rawHost.length - 1)
              : rawHost;

          final name = service.name?.isNotEmpty == true ? service.name! : host;

          // Deduplicate by host:port.
          final alreadyKnown = _discoveredNetworkDevices.any(
            (d) => d.host == host && d.port == rawPort,
          );
          if (!alreadyKnown) {
            _discoveredNetworkDevices = [
              ..._discoveredNetworkDevices,
              NetworkDevice(name: name, host: host, port: rawPort),
            ];
            notifyListeners();
          }
        }
      });

      _networkScanTimer = Timer(timeout, () {
        if (_isNetworkScanning) stopNetworkScan();
      });
    } catch (e) {
      _error = 'Network scan failed: $e';
      _isNetworkScanning = false;
      notifyListeners();
    }
  }

  /// Stop the active mDNS discovery session.
  void stopNetworkScan() {
    _networkScanTimer?.cancel();
    _networkScanTimer = null;

    final discovery = _nsdDiscovery;
    _nsdDiscovery = null;
    _isNetworkScanning = false;
    notifyListeners();

    if (discovery != null) {
      nsd.stopDiscovery(discovery).catchError((e) {
        debugPrint('stopNetworkScan: stopDiscovery error: $e');
      });
    }
  }

  /// Connect to a Meshtastic device over USB serial (OTG).
  Future<void> connectViaSerial(UsbDevice usbDevice) async {
    if (_isConnecting) return;

    _isConnecting = true;
    _userDisconnected = false;
    _reconnectAttempts = 0;
    _isReconnecting = false;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _error = null;
    final label = usbDevice.productName ?? 'USB #${usbDevice.deviceId}';
    _statusMessage = 'Connecting to $label...';
    _configLoaded = false;
    notifyListeners();

    try {
      final serial = SerialTransport(usbDevice: usbDevice);
      await serial.connect();
      _transport = serial;
      _connectionType = ConnectionType.serial;
      _connectedDevice = null; // not BLE

      await _postConnectSetup(label);
    } catch (e) {
      _error = 'USB serial connection failed: $e';
      _statusMessage = null;
      _transport = null;
      _connectionType = null;
    }

    _isConnecting = false;
    notifyListeners();
  }

  Future<void> disconnect() async {
    _userDisconnected = true;
    unawaited(PersistentRuntimeService.setBleActive(false));
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _isReconnecting = false;
    _connectionStateSubscription?.cancel();
    _connectionStateSubscription = null;
    _stopPhoneGpsSharing();
    _stopMeshPositionRelay();
    _stopMqttClientProxy();
    if (_transport != null) {
      try {
        await _transport!.disconnect();
      } catch (_) {}
      _transport = null;
      _connectionType = null;
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

    // If we're in the middle of pushing config (applyProfile), don't tear
    // down the transport — the retry logic needs it alive.
    if (_isPushingConfig || _userDisconnected || _isConnecting) {
      debugPrint('_onUnexpectedDisconnect: suppressed '
          '(pushing=$_isPushingConfig, userDisc=$_userDisconnected, '
          'connecting=$_isConnecting)');
      return;
    }

    // Clean up connection state
    _stopPhoneGpsSharing();
    _stopMeshPositionRelay();
    _stopMqttClientProxy();
    if (_transport is BleTransport) {
      (_transport as BleTransport).markDisconnected();
    }
    _transport = null;
    _connectionType = null;
    _toRadio = null;
    _fromRadio = null;
    _fromNum = null;
    _configLoaded = false;
    _deviceState = MeshtasticDeviceState();

    final device = _connectedDevice;
    _connectedDevice = null;

    if (device != null && _reconnectAttempts < _maxReconnectAttempts) {
      _isReconnecting = true;
      _statusMessage = 'Connection lost. Reconnecting to ${device.name}...';
      notifyListeners();
      _scheduleReconnect(device);
    } else {
      unawaited(PersistentRuntimeService.setBleActive(false));
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
        'Reconnecting to ${device.name} (attempt $_reconnectAttempts/$_maxReconnectAttempts)...';
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
        (s) => s.uuid.toString().toLowerCase() == meshServiceUuid,
        orElse: () => throw Exception('Meshtastic service not found'),
      );

      _toRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == toRadioCharUuid,
        orElse: () => throw Exception('toRadio not found'),
      );
      _fromRadio = meshService.characteristics.firstWhere(
        (c) => c.uuid.toString().toLowerCase() == fromRadioCharUuid,
        orElse: () => throw Exception('fromRadio not found'),
      );
      try {
        _fromNum = meshService.characteristics.firstWhere(
          (c) => c.uuid.toString().toLowerCase() == fromNumCharUuid,
        );
      } catch (_) {
        _fromNum = null;
      }

      // Re-negotiate MTU after reconnect (matches official Meshtastic app).
      try {
        final mtu = await device.device.requestMtu(512);
        debugPrint('BLE MTU re-negotiated: $mtu');
      } catch (e) {
        debugPrint('BLE MTU request failed on reconnect: $e');
      }

      // Re-create BLE transport
      _transport = BleTransport(
        device: device.device,
        toRadio: _toRadio!,
        fromRadio: _fromRadio!,
        fromNum: _fromNum,
      );
      _connectionType = ConnectionType.ble;
      unawaited(PersistentRuntimeService.setBleActive(true));

      // Re-read config
      await _readDeviceConfig();
      _configLoaded = true;

      // Restart GPS sharing and mesh relay
      _startPhoneGpsSharing();
      _startMeshPositionRelay();
      _startMqttClientProxy();

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
        unawaited(PersistentRuntimeService.setBleActive(false));
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
    if (_transport == null) return;

    _deviceState = MeshtasticDeviceState();

    // Send want_config_id with a random nonce
    final configId = Random().nextInt(0xFFFFFF) + 1;
    final wantConfig = buildWantConfigMessage(configId);
    await _transport!.writeToRadio(wantConfig);

    // Read all FromRadio responses until config_complete_id matches.
    // Use a total timeout rather than a fixed empty-read count so that
    // slower devices still have time to deliver the full config dump.
    final deadline = DateTime.now().add(const Duration(seconds: 10));

    while (DateTime.now().isBefore(deadline)) {
      // Delay between reads to give the device time to queue responses
      await Future.delayed(const Duration(milliseconds: 100));

      List<int> data;
      try {
        data = await _transport!.readFromRadio();
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
          if (nodeNum == _deviceState.myNodeNum ||
              _deviceState.myNodeNum == 0) {
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
        case 3: // fixed_pin (uint32)
          if (wt == 0) {
            _deviceState.bluetoothFixedPin = r.readVarint();
          } else {
            r.skip(wt);
          }
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
    // Protobuf fields can arrive in any order, so collect index and settings
    // bytes first, then parse settings only for the primary channel (index 0).
    int? index;
    Uint8List? settingsBytes;

    while (reader.hasMore) {
      final (field, wireType) = reader.readTag();
      switch (field) {
        case 1: // index
          index = reader.readVarint();
          break;
        case 2: // settings (raw bytes — defer parsing until index is known)
          settingsBytes = Uint8List.fromList(reader.readBytes());
          break;
        default:
          reader.skip(wireType);
      }
    }

    // Only parse settings for the primary channel (index 0 or unset = 0)
    if ((index ?? 0) != 0 || settingsBytes == null) return;

    final sub = ProtoReader(settingsBytes);
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

  /// Write a single admin message to the connected device with retry.
  Future<void> _writeAdmin(Uint8List adminPayload) async {
    if (_transport == null) throw Exception('Not connected');

    final meshPacket = buildAdminPacket(
      to: _deviceState.myNodeNum,
      from: _deviceState.myNodeNum,
      adminPayload: adminPayload,
    );
    final toRadio = buildToRadioPacket(meshPacket);

    // Retry for transient GATT failures (error 133 / FBP-code 6).
    const maxRetries = 3;
    for (var attempt = 0; attempt < maxRetries; attempt++) {
      try {
        await _transport!.writeToRadio(toRadio);
        break; // success
      } catch (e) {
        final isLastAttempt = attempt == maxRetries - 1;
        debugPrint(
            '_writeAdmin: attempt ${attempt + 1}/$maxRetries failed: $e');
        if (isLastAttempt) rethrow;
        // Wait before retrying — give BLE stack time to recover
        await Future.delayed(Duration(milliseconds: 1000 * (attempt + 1)));
        if (_transport == null) throw Exception('Device disconnected');
      }
    }

    // Delay between writes to give the firmware time to process each admin
    // message.  1500 ms is conservative but necessary to prevent GATT 133 on
    // budget Android devices with flaky BLE stacks (e.g. UMIDIGI / Unisoc).
    await Future.delayed(const Duration(milliseconds: 1500));
  }

  /// Apply a full profile preset to the connected device.
  ///
  /// If [customConfig] is provided it overrides the built-in preset, allowing
  /// the UI to let the user tweak individual settings before applying.
  ///
  /// [wifiSsid] and [wifiPsk] are included in the batched NetworkConfig write
  /// so that Wi-Fi credentials survive the commit (a standalone setWifi before
  /// the batch would be overwritten).
  Future<void> applyProfile(MeshtasticProfile profile,
      {ProfileConfig? customConfig,
      String? wifiSsid,
      String? wifiPsk,
      String? longName,
      String? shortName,
      RegionCode? region}) async {
    if (_transport == null) {
      _error = 'No device connected';
      notifyListeners();
      return;
    }

    final config = customConfig ?? ProfileConfig.presets[profile]!;
    debugPrint('applyProfile: ${profile.label}');
    debugPrint('  role=${config.role}, rebroadcast=${config.rebroadcastMode}');
    debugPrint(
        '  bluetooth=${config.bluetoothEnabled}, wifi=${config.wifiEnabled}');
    _isPushingConfig = true;
    _error = null;
    _statusMessage = 'Applying ${profile.label} profile...';
    notifyListeners();

    try {
      // Register before writes. Only Pilot becomes the live tracker;
      // infrastructure and driver profiles stay in user-owned inventory.
      final meshPurpose = _meshPurposeForProfile(profile);
      if (meshPurpose == 'tracking') {
        await _registerMeshDevice();
      } else {
        await _registerMeshDeviceInventory(meshPurpose);
      }

      // Build all admin payloads upfront.
      final writes = <MapEntry<String, Uint8List>>[];

      writes.add(MapEntry('Begin edit', buildBeginEditSettings()));

      if (longName != null && longName.isNotEmpty ||
          shortName != null && shortName.isNotEmpty) {
        writes.add(MapEntry(
            'Device name',
            buildSetOwner(
              longName: longName ?? '',
              shortName: shortName ?? '',
            )));
      }

      writes.add(MapEntry(
          'Device config',
          buildSetDeviceConfig(
            role: config.role,
            rebroadcastMode: config.rebroadcastMode,
            serialEnabled: config.serialEnabled,
            nodeInfoBroadcastSecs: config.nodeInfoBroadcastSecs,
          )));

      writes.add(MapEntry(
          'Position config',
          buildSetPositionConfig(
            positionBroadcastSecs: config.positionBroadcastSecs,
            smartEnabled: config.smartPositionEnabled,
            smartMinDistance: config.smartMinDistance,
            smartMinInterval: config.smartMinInterval,
            gpsMode: config.gpsMode,
            positionFlags: config.positionFlags,
            gpsUpdateInterval: config.gpsUpdateInterval,
          )));

      final loraRegion = region ?? _deviceState.region;
      writes.add(MapEntry(
          'LoRa radio',
          buildSetLoraConfig(
            modemPreset: config.modemPreset,
            region: loraRegion,
            hopLimit: config.hopLimit,
            txEnabled: config.txEnabled,
            txPower: config.txPower,
            sx126xRxBoostedGain: config.sx126xRxBoostedGain,
          )));

      writes.add(MapEntry(
          'Power config',
          buildSetPowerConfig(
            isPowerSaving: config.powerSaving,
            onBatteryShutdownAfterSecs: config.onBatteryShutdownAfterSecs,
            waitBluetoothSecs: config.waitBluetoothSecs,
            lsSecs: config.lsSecs,
          )));

      writes.add(MapEntry(
          'Display config',
          buildSetDisplayConfig(
            screenOnSecs: config.displayTimeoutSecs,
            autoScreenCarouselSecs: config.autoScreenCarouselSecs,
            wakeOnTapOrMotion: config.wakeOnTapOrMotion,
          )));

      writes.add(MapEntry(
          'Network config',
          buildSetNetworkConfig(
            wifiEnabled: config.wifiEnabled,
            ethEnabled: config.ethEnabled,
            wifiSsid: wifiSsid,
            wifiPsk: wifiPsk,
          )));

      writes.add(MapEntry(
          'MQTT config',
          buildSetMqttConfig(
            address: _platformMqttAddressForRadio(),
            username: _platformMqttUsername,
            password: _platformMqttPassword,
            rootTopic: _platformMqttTopicPrefix,
            encryptionEnabled: false,
            tlsEnabled: _platformMqttTlsEnabled,
            proxyToClientEnabled: config.bluetoothEnabled,
          )));

      writes.add(MapEntry(
          'Telemetry',
          buildSetTelemetryConfig(
            deviceUpdateInterval: config.deviceTelemetryEnabled
                ? config.telemetryIntervalSecs
                : 0,
            environmentMeasurementEnabled: config.environmentTelemetryEnabled,
          )));

      writes.add(MapEntry(
          'Neighbor info',
          buildSetNeighborInfoConfig(
            enabled: config.neighborInfoEnabled,
            updateIntervalSecs: config.neighborInfoIntervalSecs,
          )));

      writes.add(MapEntry(
          'Store & forward',
          buildSetStoreForwardConfig(
            enabled: config.storeForwardEnabled,
            isServer: config.storeForwardIsServer,
          )));

      Uint8List channelPsk;
      if (_platformMqttPsk != null && _platformMqttPsk!.isNotEmpty) {
        try {
          channelPsk = base64.decode(_platformMqttPsk!);
        } catch (_) {
          channelPsk = Uint8List.fromList([1]);
        }
      } else {
        channelPsk = Uint8List.fromList([1]);
      }
      writes.add(MapEntry(
          'Channel 0',
          buildSetChannel(
            index: 0,
            role: 1,
            psk: channelPsk,
            uplinkEnabled: true,
            downlinkEnabled: true,
          )));

      writes.add(MapEntry(
          'Bluetooth config',
          buildSetBluetoothConfig(
            enabled: config.bluetoothEnabled,
            mode: config.bluetoothMode,
            fixedPin: config.bluetoothMode == BlePairingMode.fixedPin
                ? config.bluetoothFixedPin
                : null,
          )));

      // ── Write loop ──
      // Send all admin messages sequentially with 1500ms delays.
      // No proactive disconnect/reconnect — on ESP32 with Wi-Fi enabled
      // the shared radio makes BLE reconnection unreliable.
      for (var i = 0; i < writes.length; i++) {
        final entry = writes[i];
        debugPrint('applyProfile: [${i + 1}/${writes.length}] ${entry.key}');
        _statusMessage = '${entry.key} (${i + 1}/${writes.length})...';
        notifyListeners();
        await _writeAdmin(entry.value);
      }

      if (region != null) _deviceState.region = region;

      // Suppress auto-reconnect — device is about to reboot intentionally.
      _userDisconnected = true;

      // Commit batch edit — device reboots immediately after receiving this.
      debugPrint('applyProfile: sending commitEditSettings');
      _statusMessage = 'Committing settings (device will reboot)...';
      notifyListeners();
      try {
        await _writeAdmin(buildCommitEditSettings());
      } catch (e) {
        debugPrint('Commit write exception (expected on reboot): $e');
      }

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
      _deviceState.blePairingMode = config.bluetoothMode;
      _deviceState.bluetoothFixedPin = config.bluetoothFixedPin;
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

    // Clean teardown if the device rebooted (commit succeeded).
    if (_userDisconnected) {
      _stopPhoneGpsSharing();
      _stopMeshPositionRelay();
      _stopMqttClientProxy();
      if (_transport is BleTransport) {
        (_transport as BleTransport).markDisconnected();
      }
      _transport = null;
      _connectionType = null;
      _toRadio = null;
      _fromRadio = null;
      _fromNum = null;
      _configLoaded = false;
      _connectedDevice = null;
      _discoveredNetworkDevices = [];
    }

    notifyListeners();

    // Clear the "Device rebooting..." message after a short delay so the
    // user sees it briefly but it doesn't stick around forever.
    if (_statusMessage != null && _error == null) {
      Future.delayed(const Duration(seconds: 5), () {
        if (_statusMessage?.contains('rebooting') == true) {
          _statusMessage = null;
          notifyListeners();
        }
      });
    }
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
      _deviceState.mqttEnabled = true;
      _deviceState.mqttProxyToClient = _deviceState.bluetoothEnabled;
      _startMqttClientProxy();
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

    // Use transport push notifications if available, otherwise poll
    final dataStream = _transport?.onDataAvailable;
    if (dataStream != null) {
      _dataAvailableSubscription = dataStream.listen(
        (_) => _drainFromRadio(),
        onError: (_) {
          // Push notifications failed — fall back to polling
          _dataAvailableSubscription?.cancel();
          _dataAvailableSubscription = null;
          _meshPollTimer = Timer.periodic(
            const Duration(seconds: 5),
            (_) => _drainFromRadio(),
          );
        },
      );
    } else {
      // No push notifications — poll periodically
      _meshPollTimer = Timer.periodic(
        const Duration(seconds: 5),
        (_) => _drainFromRadio(),
      );
    }
  }

  void _stopMeshPositionRelay() {
    _dataAvailableSubscription?.cancel();
    _dataAvailableSubscription = null;
    _meshPollTimer?.cancel();
    _meshPollTimer = null;
  }

  void _startMqttClientProxy() {
    final transport = _transport;
    if (transport == null ||
        !_deviceState.mqttEnabled ||
        !_deviceState.mqttProxyToClient) {
      _stopMqttClientProxy();
      return;
    }

    unawaited(_mqttClientProxy.start(
      deviceState: _deviceState,
      writeToRadio: transport.writeToRadio,
    ));
  }

  void _stopMqttClientProxy() {
    unawaited(_mqttClientProxy.stop());
  }

  Future<void> _drainFromRadio() async {
    if (_transport == null) return;

    // Read all available packets (up to 20 per drain cycle)
    for (var i = 0; i < 20; i++) {
      List<int> data;
      try {
        data = await _transport!.readFromRadio();
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
          // MeshPacket (field 2 in FromRadio)
          final packetBytes = reader.readBytes();
          _handleMeshPacket(Uint8List.fromList(packetBytes));
        } else if (field == 14) {
          // MQTT Client Proxy Message (device to client/phone)
          final proxyBytes = reader.readBytes();
          _mqttClientProxy.publishFromRadio(
            MqttClientProxyMessage.fromBytes(Uint8List.fromList(proxyBytes)),
          );
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
          case 2: // to (fixed32)
            mp.skip(wireType);
            break;
          case 3: // channel (varint)
            mp.skip(wireType);
            break;
          case 4: // decoded Data (length-delimited)
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

      if (payload == null) return;

      // Handle telemetry packets (portnum 67 = TELEMETRY_APP)
      if (portnum == 67) {
        _handleTelemetryPacket(fromNode, payload);
        return;
      }

      if (portnum != 3) return; // Only position packets below

      // Parse Position message
      final posReader = ProtoReader(payload);
      int? latI, lonI, alt, time, speed, heading, pdop, satsInView;

      while (posReader.hasMore) {
        final (field, wireType) = posReader.readTag();
        switch (field) {
          case 1: // latitude_i (sfixed32, wire type 5)
            if (wireType == 5) {
              latI = posReader.readSfixed32();
            } else if (wireType == 0) {
              latI = posReader.readSignedVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 2: // longitude_i (sfixed32, wire type 5)
            if (wireType == 5) {
              lonI = posReader.readSfixed32();
            } else if (wireType == 0) {
              lonI = posReader.readSignedVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 3: // altitude (int32, wire type 0)
            if (wireType == 0) {
              alt = posReader.readVarint();
            } else if (wireType == 5) {
              alt = posReader.readSfixed32();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 4: // time (fixed32, wire type 5)
            if (wireType == 5) {
              time = posReader.readFixed32();
            } else if (wireType == 0) {
              time = posReader.readVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 8: // ground_speed (uint32, wire type 0)
            if (wireType == 0) {
              speed = posReader.readVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 9: // ground_track (uint32, wire type 0)
            if (wireType == 0) {
              heading = posReader.readVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 10: // PDOP (uint32, wire type 0, ×100)
            if (wireType == 0) {
              pdop = posReader.readVarint();
            } else {
              posReader.skip(wireType);
            }
            break;
          case 13: // sats_in_view (uint32, wire type 0)
            if (wireType == 0) {
              satsInView = posReader.readVarint();
            } else {
              posReader.skip(wireType);
            }
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

      final deviceId = fromNode != null
          ? '!${fromNode.toRadixString(16).padLeft(8, '0')}'
          : null;

      // Track this device's own GPS fix for source priority
      if (fromNode != null && fromNode == _deviceState.myNodeNum) {
        _deviceGpsLat = lat;
        _deviceGpsLon = lon;
        _deviceGpsAlt = alt?.toDouble();
        _deviceGpsLastFix = time != null
            ? DateTime.fromMillisecondsSinceEpoch(time * 1000, isUtc: true)
            : DateTime.now().toUtc();
        _deviceGpsSats = satsInView;
        _deviceGpsPdop = pdop != null ? pdop / 100.0 : null;
        notifyListeners();
      }

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
    } catch (e) {
      debugPrint('[BLE] mesh position parse error: $e');
    }
  }

  /// Parse a Telemetry packet (portnum 67) and extract battery level / voltage
  /// from the DeviceMetrics sub-message.
  ///
  /// Meshtastic Telemetry protobuf layout:
  ///   field 1: time (uint32)
  ///   field 2: DeviceMetrics (sub-message)
  ///     field 1: battery_level (uint32, 0-100 or 101 = powered/no battery)
  ///     field 2: voltage (float, wire type 5 = fixed32)
  ///     field 3: channel_utilization (float)
  ///     field 4: air_util_tx (float)
  ///     field 5: uptime_seconds (uint32)
  void _handleTelemetryPacket(int? fromNode, Uint8List payload) {
    // Only care about our own device's telemetry
    if (fromNode == null || fromNode != _deviceState.myNodeNum) return;

    try {
      final tr = ProtoReader(payload);
      Uint8List? deviceMetricsBytes;

      while (tr.hasMore) {
        final (field, wireType) = tr.readTag();
        switch (field) {
          case 2: // DeviceMetrics sub-message
            deviceMetricsBytes = Uint8List.fromList(tr.readBytes());
            break;
          default:
            tr.skip(wireType);
        }
      }

      if (deviceMetricsBytes == null) return;

      final dm = ProtoReader(deviceMetricsBytes);
      int? batteryLevel;
      double? voltage;

      while (dm.hasMore) {
        final (field, wireType) = dm.readTag();
        switch (field) {
          case 1: // battery_level (uint32)
            if (wireType == 0) {
              batteryLevel = dm.readVarint();
            } else {
              dm.skip(wireType);
            }
            break;
          case 2: // voltage (float, fixed32)
            if (wireType == 5) {
              voltage = dm.readFloat();
            } else {
              dm.skip(wireType);
            }
            break;
          default:
            dm.skip(wireType);
        }
      }

      bool changed = false;
      if (batteryLevel != null && batteryLevel <= 100) {
        _deviceBatteryLevel = batteryLevel;
        changed = true;
      } else if (batteryLevel != null && batteryLevel == 101) {
        // 101 means USB-powered / no battery — show as "Powered"
        _deviceBatteryLevel = 101;
        changed = true;
      }
      if (voltage != null && voltage > 0) {
        _deviceVoltage = voltage;
        changed = true;
      }
      if (changed) notifyListeners();
    } catch (e) {
      debugPrint('[BLE] telemetry parse error: $e');
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
    if (_transport == null || _lastPhonePosition == null) return;
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
      await _transport!.writeToRadio(toRadio);
    } catch (_) {
      // Write failed — device may have disconnected
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
    _stopMqttClientProxy();
    stopScan();
    stopNetworkScan();
    disconnect();
    super.dispose();
  }
}
