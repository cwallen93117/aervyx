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
class ProfileConfig {
  final DeviceRole role;
  final RebroadcastMode rebroadcastMode;
  final GpsMode gpsMode;
  final int positionBroadcastSecs;
  final bool smartPositionEnabled;
  final int smartMinDistance;
  final int smartMinInterval;
  final ModemPreset modemPreset;
  final int hopLimit;
  final bool powerSaving;
  final bool bluetoothEnabled;
  final bool wifiEnabled;
  final int positionFlags;
  final int displayTimeoutSecs;
  final int telemetryIntervalSecs;

  const ProfileConfig({
    required this.role,
    required this.rebroadcastMode,
    required this.gpsMode,
    required this.positionBroadcastSecs,
    required this.smartPositionEnabled,
    required this.smartMinDistance,
    required this.smartMinInterval,
    required this.modemPreset,
    required this.hopLimit,
    required this.powerSaving,
    required this.bluetoothEnabled,
    required this.wifiEnabled,
    required this.positionFlags,
    required this.displayTimeoutSecs,
    required this.telemetryIntervalSecs,
  });

  /// Decode from server JSON (snake_case keys, string enum values).
  factory ProfileConfig.fromJson(Map<String, dynamic> json) {
    return ProfileConfig(
      role: _roleFromString(json['role'] as String? ?? 'client'),
      rebroadcastMode: _rebroadcastFromString(json['rebroadcast_mode'] as String? ?? 'all'),
      gpsMode: _gpsModeFromString(json['gps_mode'] as String? ?? 'enabled'),
      positionBroadcastSecs: json['position_broadcast_secs'] as int? ?? 30,
      smartPositionEnabled: json['smart_position_enabled'] as bool? ?? true,
      smartMinDistance: json['smart_min_distance'] as int? ?? 100,
      smartMinInterval: json['smart_min_interval'] as int? ?? 30,
      modemPreset: _modemFromString(json['modem_preset'] as String? ?? 'long_fast'),
      hopLimit: json['hop_limit'] as int? ?? 3,
      powerSaving: json['power_saving'] as bool? ?? false,
      bluetoothEnabled: json['bluetooth_enabled'] as bool? ?? true,
      wifiEnabled: json['wifi_enabled'] as bool? ?? false,
      positionFlags: json['position_flags'] as int? ?? PositionFlags.altitude,
      displayTimeoutSecs: json['display_timeout_secs'] as int? ?? 30,
      telemetryIntervalSecs: json['telemetry_interval_secs'] as int? ?? 86400,
    );
  }

  Map<String, dynamic> toJson() => {
    'role': _roleToString(role),
    'rebroadcast_mode': _rebroadcastToString(rebroadcastMode),
    'gps_mode': _gpsModeToString(gpsMode),
    'position_broadcast_secs': positionBroadcastSecs,
    'smart_position_enabled': smartPositionEnabled,
    'smart_min_distance': smartMinDistance,
    'smart_min_interval': smartMinInterval,
    'modem_preset': _modemToString(modemPreset),
    'hop_limit': hopLimit,
    'power_saving': powerSaving,
    'bluetooth_enabled': bluetoothEnabled,
    'wifi_enabled': wifiEnabled,
    'position_flags': positionFlags,
    'display_timeout_secs': displayTimeoutSecs,
    'telemetry_interval_secs': telemetryIntervalSecs,
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

  // ── Mutable presets (defaults overwritten by server sync) ──

  static Map<MeshtasticProfile, ProfileConfig> presets = {
    MeshtasticProfile.pilot: const ProfileConfig(
      role: DeviceRole.tracker,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      positionBroadcastSecs: 30,
      smartPositionEnabled: true,
      smartMinDistance: 100,
      smartMinInterval: 30,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: false,
      positionFlags: PositionFlags.altitude,
      displayTimeoutSecs: 30,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.driver: const ProfileConfig(
      role: DeviceRole.client,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      positionBroadcastSecs: 120,
      smartPositionEnabled: true,
      smartMinDistance: 200,
      smartMinInterval: 60,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: false,
      positionFlags: PositionFlags.altitude,
      displayTimeoutSecs: 60,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.driverWifi: const ProfileConfig(
      role: DeviceRole.client,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      positionBroadcastSecs: 60,
      smartPositionEnabled: true,
      smartMinDistance: 200,
      smartMinInterval: 30,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: true,
      positionFlags: PositionFlags.altitude,
      displayTimeoutSecs: 60,
      telemetryIntervalSecs: 86400,
    ),
    MeshtasticProfile.repeater: const ProfileConfig(
      role: DeviceRole.router,
      rebroadcastMode: RebroadcastMode.all,
      gpsMode: GpsMode.enabled,
      positionBroadcastSecs: 300,
      smartPositionEnabled: false,
      smartMinDistance: 0,
      smartMinInterval: 0,
      modemPreset: ModemPreset.longFast,
      hopLimit: 3,
      powerSaving: false,
      bluetoothEnabled: true,
      wifiEnabled: true,
      positionFlags: PositionFlags.altitude,
      displayTimeoutSecs: 0,
      telemetryIntervalSecs: 86400,
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
Uint8List buildSetDeviceConfig({
  required DeviceRole role,
  required RebroadcastMode rebroadcastMode,
}) {
  final device = ProtoWriter();
  device.writeVarint(1, role.value); // role
  device.writeVarint(6, rebroadcastMode.value); // rebroadcast_mode

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
}) {
  final pos = ProtoWriter();
  pos.writeVarint(1, positionBroadcastSecs); // position_broadcast_secs
  pos.writeBool(2, smartEnabled); // position_broadcast_smart_enabled
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
Uint8List buildSetPowerConfig({required bool isPowerSaving}) {
  final power = ProtoWriter();
  power.writeBool(1, isPowerSaving); // is_power_saving

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
}) {
  final net = ProtoWriter();
  net.writeBool(1, wifiEnabled); // wifi_enabled
  if (wifiSsid != null) net.writeString(3, wifiSsid); // wifi_ssid
  if (wifiPsk != null) net.writeString(4, wifiPsk); // wifi_psk

  final config = ProtoWriter();
  config.writeMessage(4, net); // network (Config field 4)

  final admin = ProtoWriter();
  admin.writeMessage(34, config); // set_config (AdminMessage field 34)
  return admin.toBytes();
}

/// AdminMessage: set_config with DisplayConfig (Config field 5).
Uint8List buildSetDisplayConfig({required int screenOnSecs}) {
  final display = ProtoWriter();
  display.writeVarint(1, screenOnSecs); // screen_on_secs

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
}) {
  final lora = ProtoWriter();
  lora.writeBool(1, true); // use_preset
  lora.writeVarint(2, modemPreset.value); // modem_preset
  lora.writeVarint(7, region.value); // region
  lora.writeVarint(8, hopLimit); // hop_limit
  lora.writeBool(9, txEnabled); // tx_enabled

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
}) {
  final bt = ProtoWriter();
  bt.writeBool(1, enabled); // enabled
  bt.writeVarint(2, mode.value); // mode

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
Uint8List buildSetTelemetryConfig({required int deviceUpdateInterval}) {
  final tel = ProtoWriter();
  tel.writeVarint(1, deviceUpdateInterval); // device_update_interval

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
Uint8List buildSetNeighborInfoConfig({required bool enabled}) {
  final ni = ProtoWriter();
  ni.writeBool(1, enabled); // enabled

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
