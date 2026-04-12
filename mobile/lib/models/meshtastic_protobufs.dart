/// Hand-written Dart representations of Meshtastic protobuf messages.
///
/// These are lightweight serializers/deserializers that match the Meshtastic
/// protobuf wire format. We only implement the subset needed for Aervyx
/// device configuration over BLE.
///
/// Reference: https://github.com/meshtastic/protobufs/tree/master/meshtastic
library;

import 'dart:convert';
import 'dart:typed_data';

// ═══════════════════════════════════════════════════════════════════════════════
// Enums
// ═══════════════════════════════════════════════════════════════════════════════

/// Config.DeviceConfig.Role
enum DeviceRole {
  client(0, 'Client'),
  clientMute(1, 'Client Mute'),
  router(2, 'Router'),
  routerClient(3, 'Router Client (deprecated)'),
  repeater(4, 'Repeater (deprecated)'),
  tracker(5, 'Tracker'),
  sensor(6, 'Sensor'),
  tak(7, 'TAK'),
  clientHidden(8, 'Client Hidden'),
  lostAndFound(9, 'Lost and Found'),
  takTracker(10, 'TAK Tracker'),
  routerLate(11, 'Router Late'),
  clientBase(12, 'Client Base');

  final int value;
  final String label;
  const DeviceRole(this.value, this.label);

  static DeviceRole fromValue(int v) =>
      DeviceRole.values.firstWhere((e) => e.value == v,
          orElse: () => DeviceRole.client);
}

/// Config.DeviceConfig.RebroadcastMode
enum RebroadcastMode {
  all(0, 'All'),
  allSkipDecoding(1, 'All (skip decoding)'),
  localOnly(2, 'Local Only'),
  knownOnly(3, 'Known Only'),
  none(4, 'None'),
  corePortnumsOnly(5, 'Core Portnums Only');

  final int value;
  final String label;
  const RebroadcastMode(this.value, this.label);

  static RebroadcastMode fromValue(int v) =>
      RebroadcastMode.values.firstWhere((e) => e.value == v,
          orElse: () => RebroadcastMode.all);
}

/// Config.PositionConfig.GpsMode
enum GpsMode {
  disabled(0, 'Disabled'),
  enabled(1, 'Enabled'),
  notPresent(2, 'Not Present');

  final int value;
  final String label;
  const GpsMode(this.value, this.label);

  static GpsMode fromValue(int v) =>
      GpsMode.values.firstWhere((e) => e.value == v,
          orElse: () => GpsMode.enabled);
}

/// Config.LoRaConfig.ModemPreset
enum ModemPreset {
  longFast(0, 'Long Fast'),
  longSlow(1, 'Long Slow'),
  veryLongSlow(2, 'Very Long Slow'),
  mediumSlow(3, 'Medium Slow'),
  mediumFast(4, 'Medium Fast'),
  shortSlow(5, 'Short Slow'),
  shortFast(6, 'Short Fast'),
  longModerate(7, 'Long Moderate'),
  shortTurbo(8, 'Short Turbo'),
  longTurbo(9, 'Long Turbo');

  final int value;
  final String label;
  const ModemPreset(this.value, this.label);

  static ModemPreset fromValue(int v) =>
      ModemPreset.values.firstWhere((e) => e.value == v,
          orElse: () => ModemPreset.longFast);
}

/// Config.LoRaConfig.RegionCode
enum RegionCode {
  unset(0, 'Unset'),
  us(1, 'US'),
  eu433(2, 'EU 433'),
  eu868(3, 'EU 868'),
  cn(4, 'CN'),
  jp(5, 'JP'),
  anz(6, 'ANZ'),
  kr(7, 'KR'),
  tw(8, 'TW'),
  ru(9, 'RU'),
  ind(10, 'IN'),
  nz865(11, 'NZ 865'),
  th(12, 'TH'),
  lora24(13, 'LoRa 2.4'),
  ua433(14, 'UA 433'),
  ua868(15, 'UA 868');

  final int value;
  final String label;
  const RegionCode(this.value, this.label);

  static RegionCode fromValue(int v) =>
      RegionCode.values.firstWhere((e) => e.value == v,
          orElse: () => RegionCode.unset);
}

/// Config.BluetoothConfig.PairingMode
enum BlePairingMode {
  randomPin(0, 'Random PIN'),
  fixedPin(1, 'Fixed PIN'),
  noPin(2, 'No PIN');

  final int value;
  final String label;
  const BlePairingMode(this.value, this.label);

  static BlePairingMode fromValue(int v) =>
      BlePairingMode.values.firstWhere((e) => e.value == v,
          orElse: () => BlePairingMode.randomPin);
}

/// Config.NetworkConfig.AddressMode
enum AddressMode {
  dhcp(0, 'DHCP'),
  static_(1, 'Static');

  final int value;
  final String label;
  const AddressMode(this.value, this.label);

  static AddressMode fromValue(int v) =>
      AddressMode.values.firstWhere((e) => e.value == v,
          orElse: () => AddressMode.dhcp);
}

/// Position flags bitmask.
class PositionFlags {
  static const int altitude = 0x01;
  static const int altitudeMsl = 0x02;
  static const int geoidalSeparation = 0x04;
  static const int dop = 0x08;
  static const int hvdop = 0x10;
  static const int satInView = 0x20;
  static const int seqNo = 0x40;
  static const int timestamp = 0x80;
  static const int heading = 0x100;
  static const int speed = 0x200;
}

/// PortNum — subset of port numbers we use.
class PortNum {
  static const int unknownApp = 0;
  static const int positionApp = 3;
  static const int adminApp = 6;
}

/// AdminMessage config request type.
enum ConfigType {
  deviceConfig(0),
  positionConfig(1),
  powerConfig(2),
  networkConfig(3),
  displayConfig(4),
  loraConfig(5),
  bluetoothConfig(6),
  securityConfig(7);

  final int value;
  const ConfigType(this.value);
}

/// AdminMessage module config request type.
enum ModuleConfigType {
  mqttConfig(0),
  serialConfig(1),
  extNotifConfig(2),
  storeForwardConfig(3),
  rangeTestConfig(4),
  telemetryConfig(5),
  cannedMessageConfig(6),
  audioConfig(7),
  remoteHardwareConfig(8),
  neighborInfoConfig(9);

  final int value;
  const ModuleConfigType(this.value);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Position source for phone GPS sharing
// ═══════════════════════════════════════════════════════════════════════════════

enum LocationSource {
  unset(0),
  locManual(1),
  locInternal(2),
  locExternal(3); // Phone GPS

  final int value;
  const LocationSource(this.value);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Aervyx Meshtastic Profile presets
// ═══════════════════════════════════════════════════════════════════════════════

enum MeshtasticProfile {
  pilot('Pilot'),
  driver('Driver'),
  driverWifi('Driver Wi-Fi'),
  repeater('Repeater');

  final String label;
  const MeshtasticProfile(this.label);
}

/// Preset config values for each profile.
///
/// Mirrors the curated 38-field set the admin dashboard exposes per profile.
/// Field names match the snake_case keys in
/// `backend/app/routers/site_settings.py:DEFAULT_MESH_PROFILES`. The class is
/// grouped by category (Device / Position / LoRa / Power / Bluetooth /
/// Network / Display / Modules) to mirror the official Meshtastic Android app.
class ProfileConfig {
  // Device
  final DeviceRole role;
  final RebroadcastMode rebroadcastMode;
  final int nodeInfoBroadcastSecs;
  final bool serialEnabled;

  // Position
  final GpsMode gpsMode;
  final int gpsUpdateInterval;
  final int positionBroadcastSecs;
  final bool smartPositionEnabled;
  final int smartMinDistance;
  final int smartMinInterval;
  final int positionFlags;

  // LoRa — region is intentionally NOT carried by the profile. It's
  // device-specific and the operator sets it on the mobile Meshtastic
  // settings screen on their own phone. Shipping a fleet-wide region from
  // the backend would silence radios already on a legal frequency.
  final ModemPreset modemPreset;
  final int hopLimit;
  final int txPower;
  final bool txEnabled;
  final bool sx126xRxBoostedGain;

  // Power
  final bool powerSaving;
  final int onBatteryShutdownAfterSecs;
  final int lsSecs;
  final int waitBluetoothSecs;

  // Bluetooth
  final bool bluetoothEnabled;
  final BlePairingMode bluetoothMode;
  final int bluetoothFixedPin;

  // Network (Wi-Fi SSID / PSK are device-specific and set per device
  // from the mobile Meshtastic settings screen, not fleet-wide.)
  final bool wifiEnabled;
  final bool ethEnabled;

  // Display
  final int displayTimeoutSecs;
  final int autoScreenCarouselSecs;
  final bool wakeOnTapOrMotion;

  // Modules
  final int telemetryIntervalSecs;
  final bool deviceTelemetryEnabled;
  final bool environmentTelemetryEnabled;
  final bool neighborInfoEnabled;
  final int neighborInfoIntervalSecs;
  final bool storeForwardEnabled;
  final bool storeForwardIsServer;

  const ProfileConfig({
    required this.role,
    required this.rebroadcastMode,
    this.nodeInfoBroadcastSecs = 10800,
    this.serialEnabled = true,
    required this.gpsMode,
    this.gpsUpdateInterval = 0,
    required this.positionBroadcastSecs,
    required this.smartPositionEnabled,
    required this.smartMinDistance,
    required this.smartMinInterval,
    required this.positionFlags,
    required this.modemPreset,
    required this.hopLimit,
    this.txPower = 0,
    this.txEnabled = true,
    this.sx126xRxBoostedGain = true,
    required this.powerSaving,
    this.onBatteryShutdownAfterSecs = 0,
    this.lsSecs = 300,
    this.waitBluetoothSecs = 60,
    required this.bluetoothEnabled,
    this.bluetoothMode = BlePairingMode.fixedPin,
    this.bluetoothFixedPin = 123456,
    required this.wifiEnabled,
    this.ethEnabled = false,
    required this.displayTimeoutSecs,
    this.autoScreenCarouselSecs = 0,
    this.wakeOnTapOrMotion = true,
    required this.telemetryIntervalSecs,
    this.deviceTelemetryEnabled = true,
    this.environmentTelemetryEnabled = false,
    this.neighborInfoEnabled = false,
    this.neighborInfoIntervalSecs = 14400,
    this.storeForwardEnabled = false,
    this.storeForwardIsServer = false,
  });

  /// Decode from server JSON (snake_case keys, string enum values).
  factory ProfileConfig.fromJson(Map<String, dynamic> json) {
    return ProfileConfig(
      // Device
      role: _roleFromString(json['role'] as String? ?? 'client'),
      rebroadcastMode: _rebroadcastFromString(json['rebroadcast_mode'] as String? ?? 'all'),
      nodeInfoBroadcastSecs: json['node_info_broadcast_secs'] as int? ?? 10800,
      serialEnabled: json['serial_enabled'] as bool? ?? true,
      // Position
      gpsMode: _gpsModeFromString(json['gps_mode'] as String? ?? 'enabled'),
      gpsUpdateInterval: json['gps_update_interval'] as int? ?? 0,
      positionBroadcastSecs: json['position_broadcast_secs'] as int? ?? 30,
      smartPositionEnabled: json['smart_position_enabled'] as bool? ?? true,
      smartMinDistance: json['smart_min_distance'] as int? ?? 100,
      smartMinInterval: json['smart_min_interval'] as int? ?? 30,
      positionFlags: json['position_flags'] as int? ?? PositionFlags.altitude,
      // LoRa (region is device-specific and not carried in profile JSON)
      modemPreset: _modemFromString(json['modem_preset'] as String? ?? 'long_fast'),
      hopLimit: json['hop_limit'] as int? ?? 3,
      txPower: json['tx_power'] as int? ?? 0,
      txEnabled: json['tx_enabled'] as bool? ?? true,
      sx126xRxBoostedGain: json['sx126x_rx_boosted_gain'] as bool? ?? true,
      // Power
      powerSaving: json['power_saving'] as bool? ?? false,
      onBatteryShutdownAfterSecs: json['on_battery_shutdown_after_secs'] as int? ?? 0,
      lsSecs: json['ls_secs'] as int? ?? 300,
      waitBluetoothSecs: json['wait_bluetooth_secs'] as int? ?? 60,
      // Bluetooth
      bluetoothEnabled: json['bluetooth_enabled'] as bool? ?? true,
      bluetoothMode: _blePairingFromString(json['bluetooth_mode'] as String? ?? 'fixed_pin'),
      bluetoothFixedPin: json['bluetooth_fixed_pin'] as int? ?? 123456,
      // Network
      wifiEnabled: json['wifi_enabled'] as bool? ?? false,
      ethEnabled: json['eth_enabled'] as bool? ?? false,
      // Display
      displayTimeoutSecs: json['display_timeout_secs'] as int? ?? 30,
      autoScreenCarouselSecs: json['auto_screen_carousel_secs'] as int? ?? 0,
      wakeOnTapOrMotion: json['wake_on_tap_or_motion'] as bool? ?? true,
      // Modules
      telemetryIntervalSecs: json['telemetry_interval_secs'] as int? ?? 86400,
      deviceTelemetryEnabled: json['device_telemetry_enabled'] as bool? ?? true,
      environmentTelemetryEnabled: json['environment_telemetry_enabled'] as bool? ?? false,
      neighborInfoEnabled: json['neighbor_info_enabled'] as bool? ?? false,
      neighborInfoIntervalSecs: json['neighbor_info_interval_secs'] as int? ?? 14400,
      storeForwardEnabled: json['store_forward_enabled'] as bool? ?? false,
      storeForwardIsServer: json['store_forward_is_server'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
    // Device
    'role': _roleToString(role),
    'rebroadcast_mode': _rebroadcastToString(rebroadcastMode),
    'node_info_broadcast_secs': nodeInfoBroadcastSecs,
    'serial_enabled': serialEnabled,
    // Position
    'gps_mode': _gpsModeToString(gpsMode),
    'gps_update_interval': gpsUpdateInterval,
    'position_broadcast_secs': positionBroadcastSecs,
    'smart_position_enabled': smartPositionEnabled,
    'smart_min_distance': smartMinDistance,
    'smart_min_interval': smartMinInterval,
    'position_flags': positionFlags,
    // LoRa (region intentionally omitted — set per device on the phone)
    'modem_preset': _modemToString(modemPreset),
    'hop_limit': hopLimit,
    'tx_power': txPower,
    'tx_enabled': txEnabled,
    'sx126x_rx_boosted_gain': sx126xRxBoostedGain,
    // Power
    'power_saving': powerSaving,
    'on_battery_shutdown_after_secs': onBatteryShutdownAfterSecs,
    'ls_secs': lsSecs,
    'wait_bluetooth_secs': waitBluetoothSecs,
    // Bluetooth
    'bluetooth_enabled': bluetoothEnabled,
    'bluetooth_mode': _blePairingToString(bluetoothMode),
    'bluetooth_fixed_pin': bluetoothFixedPin,
    // Network
    'wifi_enabled': wifiEnabled,
    'eth_enabled': ethEnabled,
    // Display
    'display_timeout_secs': displayTimeoutSecs,
    'auto_screen_carousel_secs': autoScreenCarouselSecs,
    'wake_on_tap_or_motion': wakeOnTapOrMotion,
    // Modules
    'telemetry_interval_secs': telemetryIntervalSecs,
    'device_telemetry_enabled': deviceTelemetryEnabled,
    'environment_telemetry_enabled': environmentTelemetryEnabled,
    'neighbor_info_enabled': neighborInfoEnabled,
    'neighbor_info_interval_secs': neighborInfoIntervalSecs,
    'store_forward_enabled': storeForwardEnabled,
    'store_forward_is_server': storeForwardIsServer,
  };

  // ── String ↔ enum helpers ──

  static DeviceRole _roleFromString(String s) => const {
    'client': DeviceRole.client, 'tracker': DeviceRole.tracker,
    'router': DeviceRole.router, 'client_mute': DeviceRole.clientMute,
    'repeater': DeviceRole.repeater, 'sensor': DeviceRole.sensor,
  }[s] ?? DeviceRole.client;

  static String _roleToString(DeviceRole r) => const {
    DeviceRole.client: 'client', DeviceRole.tracker: 'tracker',
    DeviceRole.router: 'router', DeviceRole.clientMute: 'client_mute',
    DeviceRole.repeater: 'repeater', DeviceRole.sensor: 'sensor',
  }[r] ?? 'client';

  static RebroadcastMode _rebroadcastFromString(String s) => const {
    'all': RebroadcastMode.all,
    'all_skip_decoding': RebroadcastMode.allSkipDecoding,
    'local_only': RebroadcastMode.localOnly,
    'known_only': RebroadcastMode.knownOnly,
    'none': RebroadcastMode.none,
    'core_portnums_only': RebroadcastMode.corePortnumsOnly,
  }[s] ?? RebroadcastMode.all;

  static String _rebroadcastToString(RebroadcastMode m) => const {
    RebroadcastMode.all: 'all',
    RebroadcastMode.allSkipDecoding: 'all_skip_decoding',
    RebroadcastMode.localOnly: 'local_only',
    RebroadcastMode.knownOnly: 'known_only',
    RebroadcastMode.none: 'none',
    RebroadcastMode.corePortnumsOnly: 'core_portnums_only',
  }[m] ?? 'all';

  static GpsMode _gpsModeFromString(String s) => const {
    'disabled': GpsMode.disabled, 'enabled': GpsMode.enabled,
    'not_present': GpsMode.notPresent,
  }[s] ?? GpsMode.enabled;

  static String _gpsModeToString(GpsMode m) => const {
    GpsMode.disabled: 'disabled', GpsMode.enabled: 'enabled',
    GpsMode.notPresent: 'not_present',
  }[m] ?? 'enabled';

  static ModemPreset _modemFromString(String s) => const {
    'long_fast': ModemPreset.longFast, 'long_slow': ModemPreset.longSlow,
    'very_long_slow': ModemPreset.veryLongSlow, 'medium_slow': ModemPreset.mediumSlow,
    'medium_fast': ModemPreset.mediumFast, 'short_slow': ModemPreset.shortSlow,
    'short_fast': ModemPreset.shortFast, 'long_moderate': ModemPreset.longModerate,
    'short_turbo': ModemPreset.shortTurbo, 'long_turbo': ModemPreset.longTurbo,
  }[s] ?? ModemPreset.longFast;

  static String _modemToString(ModemPreset m) => const {
    ModemPreset.longFast: 'long_fast', ModemPreset.longSlow: 'long_slow',
    ModemPreset.veryLongSlow: 'very_long_slow', ModemPreset.mediumSlow: 'medium_slow',
    ModemPreset.mediumFast: 'medium_fast', ModemPreset.shortSlow: 'short_slow',
    ModemPreset.shortFast: 'short_fast', ModemPreset.longModerate: 'long_moderate',
    ModemPreset.shortTurbo: 'short_turbo', ModemPreset.longTurbo: 'long_turbo',
  }[m] ?? 'long_fast';

  // _regionFromString / _regionToString removed: region is no longer carried
  // by the profile JSON. The RegionCode enum itself is still used elsewhere
  // (BleService.deviceState.region, the Meshtastic settings dropdown).

  static BlePairingMode _blePairingFromString(String s) => const {
    'random_pin': BlePairingMode.randomPin,
    'fixed_pin': BlePairingMode.fixedPin,
    'no_pin': BlePairingMode.noPin,
  }[s] ?? BlePairingMode.randomPin;

  static String _blePairingToString(BlePairingMode m) => const {
    BlePairingMode.randomPin: 'random_pin',
    BlePairingMode.fixedPin: 'fixed_pin',
    BlePairingMode.noPin: 'no_pin',
  }[m] ?? 'random_pin';

  // ── Mutable presets (defaults overwritten by server sync) ──

  static Map<MeshtasticProfile, ProfileConfig> presets = {
    MeshtasticProfile.pilot: const ProfileConfig(
      role: DeviceRole.tracker,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      gpsUpdateInterval: 30,
      positionBroadcastSecs: 30,
      smartPositionEnabled: true,
      smartMinDistance: 100,
      smartMinInterval: 30,
      positionFlags: PositionFlags.altitude,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: false,
      displayTimeoutSecs: 30,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.driver: const ProfileConfig(
      role: DeviceRole.client,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      gpsUpdateInterval: 60,
      positionBroadcastSecs: 120,
      smartPositionEnabled: true,
      smartMinDistance: 200,
      smartMinInterval: 60,
      positionFlags: PositionFlags.altitude,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: false,
      displayTimeoutSecs: 60,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.driverWifi: const ProfileConfig(
      role: DeviceRole.client,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      gpsUpdateInterval: 30,
      positionBroadcastSecs: 60,
      smartPositionEnabled: true,
      smartMinDistance: 200,
      smartMinInterval: 30,
      positionFlags: PositionFlags.altitude,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      // Bluetooth stays on so headless devices can't lock admins out.
      // On ESP32 with Wi-Fi enabled, the firmware may still disable BT at
      // runtime, but we declare our intent here.
      bluetoothEnabled: true,
      wifiEnabled: true,
      displayTimeoutSecs: 60,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.repeater: const ProfileConfig(
      role: DeviceRole.router,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      gpsUpdateInterval: 0,
      positionBroadcastSecs: 300,
      smartPositionEnabled: false,
      smartMinDistance: 0,
      smartMinInterval: 0,
      positionFlags: PositionFlags.altitude,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: true,
      displayTimeoutSecs: 0,
      wakeOnTapOrMotion: false,
      telemetryIntervalSecs: 86400,
      neighborInfoEnabled: true,
      storeForwardEnabled: true,
      storeForwardIsServer: true,
    ),
  };

  /// Profile key mapping for server JSON (snake_case).
  static const _profileKeys = {
    'pilot': MeshtasticProfile.pilot,
    'driver': MeshtasticProfile.driver,
    'driver_wifi': MeshtasticProfile.driverWifi,
    'repeater': MeshtasticProfile.repeater,
  };

  /// Replace presets with values from the server response.
  static void updatePresetsFromServer(Map<String, dynamic> json) {
    for (final entry in _profileKeys.entries) {
      final data = json[entry.key];
      if (data is Map<String, dynamic>) {
        presets[entry.value] = ProfileConfig.fromJson(data);
      }
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Lightweight protobuf encoder/decoder
//
// Meshtastic BLE uses raw protobuf (no framing). Each BLE write/read is one
// protobuf message. We implement a minimal encoder/decoder rather than pulling
// in the full protoc toolchain.
// ═══════════════════════════════════════════════════════════════════════════════

/// Minimal protobuf wire-format writer.
class ProtoWriter {
  final BytesBuilder _buf = BytesBuilder();

  Uint8List toBytes() => _buf.toBytes();

  void writeVarint(int fieldNumber, int value) {
    _writeTag(fieldNumber, 0); // wire type 0 = varint
    _writeRawVarint(value);
  }

  void writeBool(int fieldNumber, bool value) {
    writeVarint(fieldNumber, value ? 1 : 0);
  }

  void writeString(int fieldNumber, String value) {
    final bytes = utf8.encode(value);
    _writeTag(fieldNumber, 2); // wire type 2 = length-delimited
    _writeRawVarint(bytes.length);
    _buf.add(bytes);
  }

  void writeBytes(int fieldNumber, Uint8List value) {
    _writeTag(fieldNumber, 2);
    _writeRawVarint(value.length);
    _buf.add(value);
  }

  void writeFixed32(int fieldNumber, int value) {
    _writeTag(fieldNumber, 5); // wire type 5 = 32-bit
    _buf.add(Uint8List(4)..buffer.asByteData().setUint32(0, value, Endian.little));
  }

  void writeSfixed32(int fieldNumber, int value) {
    _writeTag(fieldNumber, 5); // wire type 5 = 32-bit
    _buf.add(Uint8List(4)..buffer.asByteData().setInt32(0, value, Endian.little));
  }

  void writeFloat(int fieldNumber, double value) {
    _writeTag(fieldNumber, 5);
    final bd = ByteData(4);
    bd.setFloat32(0, value, Endian.little);
    _buf.add(bd.buffer.asUint8List());
  }

  /// Write a nested message as a length-delimited field.
  void writeMessage(int fieldNumber, ProtoWriter nested) {
    final bytes = nested.toBytes();
    _writeTag(fieldNumber, 2);
    _writeRawVarint(bytes.length);
    _buf.add(bytes);
  }

  void _writeTag(int fieldNumber, int wireType) {
    _writeRawVarint((fieldNumber << 3) | wireType);
  }

  void _writeRawVarint(int value) {
    // Handle negative values (two's complement for signed varints)
    var v = value & 0xFFFFFFFFFFFFFFFF;
    while (v > 0x7F) {
      _buf.addByte((v & 0x7F) | 0x80);
      v >>= 7;
    }
    _buf.addByte(v & 0x7F);
  }
}

/// Minimal protobuf wire-format reader.
class ProtoReader {
  final Uint8List _data;
  int _pos = 0;

  ProtoReader(this._data);

  bool get hasMore => _pos < _data.length;

  /// Read the next field tag. Returns (fieldNumber, wireType).
  (int, int) readTag() {
    final v = _readRawVarint();
    return (v >> 3, v & 0x7);
  }

  int readVarint() => _readRawVarint();

  /// Read a zigzag-encoded signed varint (sint32/sint64).
  int readSignedVarint() {
    final n = _readRawVarint();
    return (n >> 1) ^ -(n & 1);
  }

  bool readBool() => _readRawVarint() != 0;

  String readString() {
    final len = _readRawVarint();
    final s = utf8.decode(_data.sublist(_pos, _pos + len));
    _pos += len;
    return s;
  }

  Uint8List readBytes() {
    final len = _readRawVarint();
    final b = Uint8List.fromList(_data.sublist(_pos, _pos + len));
    _pos += len;
    return b;
  }

  int readFixed32() {
    final v = ByteData.sublistView(_data, _pos, _pos + 4)
        .getUint32(0, Endian.little);
    _pos += 4;
    return v;
  }

  int readSfixed32() {
    final v = ByteData.sublistView(_data, _pos, _pos + 4)
        .getInt32(0, Endian.little);
    _pos += 4;
    return v;
  }

  double readFloat() {
    final v = ByteData.sublistView(_data, _pos, _pos + 4)
        .getFloat32(0, Endian.little);
    _pos += 4;
    return v;
  }

  /// Read a length-delimited sub-message and return a new reader for it.
  ProtoReader readMessageReader() {
    final bytes = readBytes();
    return ProtoReader(bytes);
  }

  /// Skip an unknown field based on its wire type.
  void skip(int wireType) {
    switch (wireType) {
      case 0:
        _readRawVarint();
        break;
      case 1: // 64-bit
        _pos += 8;
        break;
      case 2: // length-delimited
        final len = _readRawVarint();
        _pos += len;
        break;
      case 5: // 32-bit
        _pos += 4;
        break;
    }
  }

  int _readRawVarint() {
    int result = 0;
    int shift = 0;
    while (true) {
      final byte = _data[_pos++];
      result |= (byte & 0x7F) << shift;
      if ((byte & 0x80) == 0) return result;
      shift += 7;
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// High-level message builders for Meshtastic BLE protocol
// ═══════════════════════════════════════════════════════════════════════════════

/// Build a ToRadio message requesting full config dump.
Uint8List buildWantConfigMessage(int configId) {
  final w = ProtoWriter();
  // ToRadio field 3 = want_config_id (uint32)
  w.writeVarint(3, configId);
  return w.toBytes();
}

/// Build a ToRadio message containing a MeshPacket.
Uint8List buildToRadioPacket(Uint8List meshPacketBytes) {
  final w = ProtoWriter();
  // ToRadio field 1 = packet (MeshPacket)
  w.writeBytes(1, meshPacketBytes);
  return w.toBytes();
}

/// Build a MeshPacket wrapping an AdminMessage.
Uint8List buildAdminPacket({
  required int to,
  required int from,
  required Uint8List adminPayload,
  bool wantAck = true,
}) {
  // Build Data sub-message
  final data = ProtoWriter();
  data.writeVarint(1, PortNum.adminApp); // portnum
  data.writeBytes(2, adminPayload); // payload

  // Build MeshPacket
  final pkt = ProtoWriter();
  pkt.writeFixed32(1, from); // from (fixed32)
  pkt.writeFixed32(2, to); // to (fixed32)
  pkt.writeMessage(4, data); // decoded (Data, field 4)
  if (wantAck) pkt.writeBool(10, true); // want_ack (field 10)

  return pkt.toBytes();
}

/// Build a MeshPacket wrapping a Position (for phone GPS sharing).
Uint8List buildPositionPacket({
  required int to,
  required int from,
  required double lat,
  required double lon,
  required double alt,
  required int time,
  int? groundSpeed,
  int? groundTrack,
}) {
  // Build Position sub-message
  final pos = ProtoWriter();
  pos.writeSfixed32(1, (lat * 1e7).round()); // latitude_i (sfixed32)
  pos.writeSfixed32(2, (lon * 1e7).round()); // longitude_i (sfixed32)
  pos.writeVarint(3, alt.round()); // altitude (int32)
  pos.writeFixed32(4, time); // time (fixed32)
  pos.writeVarint(5, LocationSource.locExternal.value); // location_source
  if (groundSpeed != null) pos.writeVarint(15, groundSpeed); // ground_speed
  if (groundTrack != null) pos.writeVarint(16, groundTrack); // ground_track

  // Build Data sub-message
  final data = ProtoWriter();
  data.writeVarint(1, PortNum.positionApp); // portnum
  data.writeBytes(2, pos.toBytes()); // payload

  // Build MeshPacket
  final pkt = ProtoWriter();
  pkt.writeFixed32(1, from); // from (fixed32)
  pkt.writeFixed32(2, to); // to (fixed32)
  pkt.writeMessage(4, data); // decoded (Data, field 4)

  return pkt.toBytes();
}

// ═══════════════════════════════════════════════════════════════════════════════
// AdminMessage builders
// ═══════════════════════════════════════════════════════════════════════════════

/// AdminMessage: begin_edit_settings = true (field 64)
Uint8List buildBeginEditSettings() {
  final w = ProtoWriter();
  w.writeBool(64, true);
  return w.toBytes();
}

/// AdminMessage: commit_edit_settings = true (field 65)
Uint8List buildCommitEditSettings() {
  final w = ProtoWriter();
  w.writeBool(65, true);
  return w.toBytes();
}

/// AdminMessage: set_owner (field 3) — set long name, short name.
Uint8List buildSetOwner({required String longName, required String shortName}) {
  final user = ProtoWriter();
  user.writeString(2, longName); // long_name
  user.writeString(3, shortName); // short_name

  final admin = ProtoWriter();
  admin.writeMessage(32, user); // set_owner (AdminMessage field 32)
  return admin.toBytes();
}

/// AdminMessage: set_config (field 34) with DeviceConfig (Config field 1).
///
/// Tag numbers per upstream meshtastic/protobufs/meshtastic/config.proto.
Uint8List buildSetDeviceConfig({
  required DeviceRole role,
  required RebroadcastMode rebroadcastMode,
  bool? serialEnabled,
  int? nodeInfoBroadcastSecs,
}) {
  final device = ProtoWriter();
  device.writeVarint(1, role.value); // role
  if (serialEnabled != null) device.writeBool(2, serialEnabled); // serial_enabled
  device.writeVarint(6, rebroadcastMode.value); // rebroadcast_mode
  if (nodeInfoBroadcastSecs != null) {
    device.writeVarint(7, nodeInfoBroadcastSecs); // node_info_broadcast_secs
  }

  final config = ProtoWriter();
  config.writeMessage(1, device); // device (Config field 1)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with PositionConfig (Config field 2).
Uint8List buildSetPositionConfig({
  required int positionBroadcastSecs,
  required bool smartEnabled,
  required int smartMinDistance,
  required int smartMinInterval,
  required GpsMode gpsMode,
  required int positionFlags,
  int? gpsUpdateInterval,
}) {
  final pos = ProtoWriter();
  pos.writeVarint(1, positionBroadcastSecs); // position_broadcast_secs
  pos.writeBool(2, smartEnabled); // position_broadcast_smart_enabled
  if (gpsUpdateInterval != null) {
    pos.writeVarint(5, gpsUpdateInterval); // gps_update_interval
  }
  pos.writeVarint(7, positionFlags); // position_flags
  pos.writeVarint(10, smartMinDistance); // broadcast_smart_minimum_distance
  pos.writeVarint(11, smartMinInterval); // broadcast_smart_minimum_interval_secs
  pos.writeVarint(13, gpsMode.value); // gps_mode

  final config = ProtoWriter();
  config.writeMessage(2, pos); // position (Config field 2)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with PowerConfig (Config field 3).
Uint8List buildSetPowerConfig({
  required bool isPowerSaving,
  int? onBatteryShutdownAfterSecs,
  int? waitBluetoothSecs,
  int? lsSecs,
}) {
  final power = ProtoWriter();
  power.writeBool(1, isPowerSaving); // is_power_saving
  if (onBatteryShutdownAfterSecs != null) {
    power.writeVarint(2, onBatteryShutdownAfterSecs); // on_battery_shutdown_after_secs
  }
  if (waitBluetoothSecs != null) {
    power.writeVarint(4, waitBluetoothSecs); // wait_bluetooth_secs
  }
  if (lsSecs != null) {
    power.writeVarint(7, lsSecs); // ls_secs
  }

  final config = ProtoWriter();
  config.writeMessage(3, power); // power (Config field 3)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with NetworkConfig (Config field 4).
Uint8List buildSetNetworkConfig({
  required bool wifiEnabled,
  String? wifiSsid,
  String? wifiPsk,
  bool? ethEnabled,
}) {
  final net = ProtoWriter();
  net.writeBool(1, wifiEnabled); // wifi_enabled
  if (wifiSsid != null) net.writeString(3, wifiSsid); // wifi_ssid
  if (wifiPsk != null) net.writeString(4, wifiPsk); // wifi_psk
  if (ethEnabled != null) net.writeBool(6, ethEnabled); // eth_enabled

  final config = ProtoWriter();
  config.writeMessage(4, net); // network (Config field 4)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with DisplayConfig (Config field 5).
Uint8List buildSetDisplayConfig({
  required int screenOnSecs,
  int? autoScreenCarouselSecs,
  bool? wakeOnTapOrMotion,
}) {
  final display = ProtoWriter();
  display.writeVarint(1, screenOnSecs); // screen_on_secs
  if (autoScreenCarouselSecs != null) {
    display.writeVarint(3, autoScreenCarouselSecs); // auto_screen_carousel_secs
  }
  if (wakeOnTapOrMotion != null) {
    display.writeBool(10, wakeOnTapOrMotion); // wake_on_tap_or_motion
  }

  final config = ProtoWriter();
  config.writeMessage(5, display); // display (Config field 5)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with LoRaConfig (Config field 6).
Uint8List buildSetLoraConfig({
  required ModemPreset modemPreset,
  required RegionCode region,
  required int hopLimit,
  bool txEnabled = true,
  int? txPower,
  bool? sx126xRxBoostedGain,
}) {
  final lora = ProtoWriter();
  lora.writeBool(1, true); // use_preset
  lora.writeVarint(2, modemPreset.value); // modem_preset
  lora.writeVarint(7, region.value); // region
  lora.writeVarint(8, hopLimit); // hop_limit
  lora.writeBool(9, txEnabled); // tx_enabled
  if (txPower != null) lora.writeVarint(10, txPower); // tx_power
  if (sx126xRxBoostedGain != null) {
    lora.writeBool(13, sx126xRxBoostedGain); // sx126x_rx_boosted_gain
  }

  final config = ProtoWriter();
  config.writeMessage(6, lora); // lora (Config field 6)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with BluetoothConfig (Config field 7).
Uint8List buildSetBluetoothConfig({
  required bool enabled,
  BlePairingMode mode = BlePairingMode.randomPin,
  int? fixedPin,
}) {
  final bt = ProtoWriter();
  bt.writeBool(1, enabled); // enabled
  bt.writeVarint(2, mode.value); // mode
  if (fixedPin != null) bt.writeVarint(3, fixedPin); // fixed_pin

  final config = ProtoWriter();
  config.writeMessage(7, bt); // bluetooth (Config field 7)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_module_config with MQTTConfig (ModuleConfig field 1).
/// MQTT is always enabled — not user-configurable.
Uint8List buildSetMqttConfig({
  required String address,
  String? username,
  String? password,
  required String rootTopic,
  bool encryptionEnabled = true,
  bool tlsEnabled = false,
  bool proxyToClientEnabled = false,
}) {
  final mqtt = ProtoWriter();
  mqtt.writeBool(1, true); // enabled — always on
  mqtt.writeString(2, address); // address
  if (username != null) mqtt.writeString(3, username); // username
  if (password != null) mqtt.writeString(4, password); // password
  mqtt.writeBool(5, encryptionEnabled); // encryption_enabled
  mqtt.writeBool(7, tlsEnabled); // tls_enabled
  mqtt.writeString(8, rootTopic); // root
  mqtt.writeBool(9, proxyToClientEnabled); // proxy_to_client_enabled

  final module = ProtoWriter();
  module.writeMessage(1, mqtt); // mqtt (ModuleConfig field 1)

  final admin = ProtoWriter();
  admin.writeMessage(35, module); // set_module_config (AdminMessage field 35)
  return admin.toBytes();
}

/// AdminMessage: set_module_config with TelemetryConfig (ModuleConfig field 6).
Uint8List buildSetTelemetryConfig({
  required int deviceUpdateInterval,
  bool? environmentMeasurementEnabled,
}) {
  final tel = ProtoWriter();
  tel.writeVarint(1, deviceUpdateInterval); // device_update_interval
  if (environmentMeasurementEnabled != null) {
    tel.writeBool(3, environmentMeasurementEnabled); // environment_measurement_enabled
  }

  final module = ProtoWriter();
  module.writeMessage(6, tel); // telemetry (ModuleConfig field 6)

  final admin = ProtoWriter();
  admin.writeMessage(35, module); // set_module_config (AdminMessage field 35)
  return admin.toBytes();
}

/// AdminMessage: set_module_config with StoreForwardConfig (ModuleConfig field 4).
Uint8List buildSetStoreForwardConfig({required bool enabled, bool isServer = false}) {
  final sf = ProtoWriter();
  sf.writeBool(1, enabled); // enabled
  if (isServer) sf.writeBool(6, true); // is_server (field 6)

  final module = ProtoWriter();
  module.writeMessage(4, sf); // store_forward (ModuleConfig field 4)

  final admin = ProtoWriter();
  admin.writeMessage(35, module); // set_module_config (AdminMessage field 35)
  return admin.toBytes();
}

/// AdminMessage: set_module_config with NeighborInfoConfig (ModuleConfig field 10).
Uint8List buildSetNeighborInfoConfig({
  required bool enabled,
  int? updateIntervalSecs,
}) {
  final ni = ProtoWriter();
  ni.writeBool(1, enabled); // enabled
  if (updateIntervalSecs != null) {
    ni.writeVarint(2, updateIntervalSecs); // update_interval
  }

  final module = ProtoWriter();
  module.writeMessage(10, ni); // neighbor_info (ModuleConfig field 10)

  final admin = ProtoWriter();
  admin.writeMessage(35, module); // set_module_config (AdminMessage field 35)
  return admin.toBytes();
}

/// AdminMessage: set_channel (field 33).
Uint8List buildSetChannel({
  required int index,
  required int role, // 0=DISABLED, 1=PRIMARY, 2=SECONDARY
  String? name,
  Uint8List? psk,
  bool? uplinkEnabled,
  bool? downlinkEnabled,
}) {
  final settings = ProtoWriter();
  if (psk != null) settings.writeBytes(2, psk); // psk (ChannelSettings field 2)
  if (name != null) settings.writeString(3, name); // name (ChannelSettings field 3)
  if (uplinkEnabled != null) settings.writeBool(5, uplinkEnabled);
  if (downlinkEnabled != null) settings.writeBool(6, downlinkEnabled);

  final channel = ProtoWriter();
  channel.writeVarint(1, index); // index
  channel.writeMessage(2, settings); // settings
  channel.writeVarint(3, role); // role

  final admin = ProtoWriter();
  admin.writeMessage(33, channel); // set_channel (AdminMessage field 33)
  return admin.toBytes();
}

/// AdminMessage: get_config_request (field 5).
Uint8List buildGetConfigRequest(ConfigType type) {
  final w = ProtoWriter();
  w.writeVarint(5, type.value); // get_config_request (AdminMessage field 5)
  return w.toBytes();
}

/// AdminMessage: get_module_config_request (field 7).
Uint8List buildGetModuleConfigRequest(ModuleConfigType type) {
  final w = ProtoWriter();
  w.writeVarint(7, type.value); // get_module_config_request (AdminMessage field 7)
  return w.toBytes();
}

/// AdminMessage: reboot_seconds (field 97).
Uint8List buildReboot({int seconds = 5}) {
  final w = ProtoWriter();
  w.writeVarint(97, seconds); // reboot_seconds (AdminMessage field 97)
  return w.toBytes();
}

// ═══════════════════════════════════════════════════════════════════════════════
// Parsed device state — populated by reading the config dump from BLE
// ═══════════════════════════════════════════════════════════════════════════════

/// Full device state read from a connected Meshtastic device.
class MeshtasticDeviceState {
  int myNodeNum = 0;
  String? firmwareVersion;
  String longName = '';
  String shortName = '';
  DeviceRole role = DeviceRole.client;
  RebroadcastMode rebroadcastMode = RebroadcastMode.all;

  // Position
  GpsMode gpsMode = GpsMode.enabled;
  int positionBroadcastSecs = 900;
  bool smartPositionEnabled = true;
  int smartMinDistance = 100;
  int smartMinInterval = 30;
  int positionFlags = PositionFlags.altitude;

  // Power
  bool isPowerSaving = false;

  // Network
  bool wifiEnabled = false;
  String wifiSsid = '';
  String wifiPsk = '';

  // Display
  int screenOnSecs = 60;

  // LoRa
  ModemPreset modemPreset = ModemPreset.longFast;
  RegionCode region = RegionCode.unset;
  int hopLimit = 3;
  bool txEnabled = true;

  // Bluetooth
  bool bluetoothEnabled = true;
  BlePairingMode blePairingMode = BlePairingMode.randomPin;

  // MQTT
  bool mqttEnabled = false;
  String mqttAddress = '';
  String mqttUsername = '';
  String mqttPassword = '';
  String mqttRootTopic = 'msh';
  bool mqttEncryptionEnabled = true;
  bool mqttTlsEnabled = false;
  bool mqttProxyToClient = false;

  // Telemetry
  int telemetryDeviceInterval = 900;

  // Channel (primary)
  String channelName = '';
  bool channelUplinkEnabled = false;
  bool channelDownlinkEnabled = false;

  // Store & Forward
  bool storeForwardEnabled = false;
  bool storeForwardIsServer = false;

  // Neighbor Info
  bool neighborInfoEnabled = false;
}
