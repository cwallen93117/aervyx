import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:aervyx_mobile/models/meshtastic_protobufs.dart';
import 'package:aervyx_mobile/services/mqtt_client_proxy_service.dart';

void main() {
  // ═══════════════════════════════════════════════════════════════════════════
  // ProtoWriter tests
  // ═══════════════════════════════════════════════════════════════════════════

  group('ProtoWriter varint encoding', () {
    test('encodes small varint (single byte)', () {
      final w = ProtoWriter();
      w.writeVarint(1, 5); // field 1, value 5
      final bytes = w.toBytes();

      // Tag: (1 << 3) | 0 = 0x08, Value: 5
      expect(bytes[0], 0x08);
      expect(bytes[1], 5);
      expect(bytes.length, 2);
    });

    test('encodes varint value 127 in one byte', () {
      final w = ProtoWriter();
      w.writeVarint(1, 127);
      final bytes = w.toBytes();

      expect(bytes[0], 0x08); // tag
      expect(bytes[1], 127); // 127 fits in one byte
      expect(bytes.length, 2);
    });

    test('encodes varint value 128 in two bytes', () {
      final w = ProtoWriter();
      w.writeVarint(1, 128);
      final bytes = w.toBytes();

      expect(bytes[0], 0x08); // tag
      // 128 = 0x80 → varint: [0x80, 0x01]
      expect(bytes[1], 0x80);
      expect(bytes[2], 0x01);
      expect(bytes.length, 3);
    });

    test('encodes large varint value 300', () {
      final w = ProtoWriter();
      w.writeVarint(1, 300);
      final bytes = w.toBytes();

      expect(bytes[0], 0x08); // tag
      // 300 = 0x12C → varint: [0xAC, 0x02]
      expect(bytes[1], 0xAC);
      expect(bytes[2], 0x02);
    });

    test('encodes varint with higher field number', () {
      final w = ProtoWriter();
      w.writeVarint(15, 1);
      final bytes = w.toBytes();

      // Tag: (15 << 3) | 0 = 120 = 0x78
      expect(bytes[0], 0x78);
      expect(bytes[1], 1);
    });

    test('encodes varint with field number > 15 (multi-byte tag)', () {
      final w = ProtoWriter();
      w.writeVarint(16, 1);
      final bytes = w.toBytes();

      // Tag: (16 << 3) | 0 = 128 → varint: [0x80, 0x01]
      expect(bytes[0], 0x80);
      expect(bytes[1], 0x01);
      // Value: 1
      expect(bytes[2], 1);
    });
  });

  group('ProtoWriter fixed32 and sfixed32 encoding', () {
    test('encodes fixed32 correctly', () {
      final w = ProtoWriter();
      w.writeFixed32(1, 0x12345678);
      final bytes = w.toBytes();

      // Tag: (1 << 3) | 5 = 0x0D (wire type 5)
      expect(bytes[0], 0x0D);
      // Little-endian: 0x78, 0x56, 0x34, 0x12
      expect(bytes[1], 0x78);
      expect(bytes[2], 0x56);
      expect(bytes[3], 0x34);
      expect(bytes[4], 0x12);
    });

    test('encodes sfixed32 positive value', () {
      final w = ProtoWriter();
      w.writeSfixed32(1, 42);
      final bytes = w.toBytes();

      expect(bytes[0], 0x0D); // tag
      // 42 in little-endian: 0x2A, 0x00, 0x00, 0x00
      expect(bytes[1], 0x2A);
      expect(bytes[2], 0x00);
      expect(bytes[3], 0x00);
      expect(bytes[4], 0x00);
    });

    test('encodes sfixed32 negative value', () {
      final w = ProtoWriter();
      w.writeSfixed32(1, -1);
      final bytes = w.toBytes();

      expect(bytes[0], 0x0D); // tag
      // -1 in two's complement little-endian: 0xFF, 0xFF, 0xFF, 0xFF
      expect(bytes[1], 0xFF);
      expect(bytes[2], 0xFF);
      expect(bytes[3], 0xFF);
      expect(bytes[4], 0xFF);
    });
  });

  group('ProtoWriter string encoding', () {
    test('encodes string correctly (length-delimited)', () {
      final w = ProtoWriter();
      w.writeString(1, 'hello');
      final bytes = w.toBytes();

      // Tag: (1 << 3) | 2 = 0x0A (wire type 2)
      expect(bytes[0], 0x0A);
      // Length: 5
      expect(bytes[1], 5);
      // UTF-8 bytes of "hello"
      expect(bytes[2], 0x68); // h
      expect(bytes[3], 0x65); // e
      expect(bytes[4], 0x6C); // l
      expect(bytes[5], 0x6C); // l
      expect(bytes[6], 0x6F); // o
    });

    test('encodes empty string', () {
      final w = ProtoWriter();
      w.writeString(1, '');
      final bytes = w.toBytes();

      expect(bytes[0], 0x0A); // tag
      expect(bytes[1], 0); // length 0
      expect(bytes.length, 2);
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // ProtoReader tests
  // ═══════════════════════════════════════════════════════════════════════════

  group('ProtoReader varint reading', () {
    test('reads single-byte varint', () {
      // Field 1, varint wire type, value 5
      final data = Uint8List.fromList([0x08, 0x05]);
      final reader = ProtoReader(data);

      final (fieldNumber, wireType) = reader.readTag();
      expect(fieldNumber, 1);
      expect(wireType, 0);

      final value = reader.readVarint();
      expect(value, 5);
      expect(reader.hasMore, false);
    });

    test('reads multi-byte varint', () {
      // Field 1, varint wire type, value 300 = [0xAC, 0x02]
      final data = Uint8List.fromList([0x08, 0xAC, 0x02]);
      final reader = ProtoReader(data);

      reader.readTag();
      final value = reader.readVarint();
      expect(value, 300);
    });
  });

  group('ProtoReader fixed32 and sfixed32 reading', () {
    test('reads fixed32', () {
      // Field 1, wire type 5, 0x12345678 in little-endian
      final data = Uint8List.fromList([0x0D, 0x78, 0x56, 0x34, 0x12]);
      final reader = ProtoReader(data);

      final (fieldNumber, wireType) = reader.readTag();
      expect(fieldNumber, 1);
      expect(wireType, 5);

      final value = reader.readFixed32();
      expect(value, 0x12345678);
    });

    test('reads sfixed32 negative value', () {
      // Field 1, wire type 5, -1 = 0xFFFFFFFF little-endian
      final data = Uint8List.fromList([0x0D, 0xFF, 0xFF, 0xFF, 0xFF]);
      final reader = ProtoReader(data);

      reader.readTag();
      final value = reader.readSfixed32();
      expect(value, -1);
    });

    test('reads sfixed32 positive value', () {
      // Field 1, wire type 5, 42 = 0x2A000000 little-endian
      final data = Uint8List.fromList([0x0D, 0x2A, 0x00, 0x00, 0x00]);
      final reader = ProtoReader(data);

      reader.readTag();
      final value = reader.readSfixed32();
      expect(value, 42);
    });
  });

  group('ProtoReader length-delimited reading', () {
    test('reads string', () {
      // Field 1, wire type 2, length 5, "hello"
      final data = Uint8List.fromList([
        0x0A,
        0x05,
        0x68,
        0x65,
        0x6C,
        0x6C,
        0x6F,
      ]);
      final reader = ProtoReader(data);

      final (fieldNumber, wireType) = reader.readTag();
      expect(fieldNumber, 1);
      expect(wireType, 2);

      final value = reader.readString();
      expect(value, 'hello');
    });

    test('reads bytes', () {
      final data = Uint8List.fromList([0x0A, 0x03, 0x01, 0x02, 0x03]);
      final reader = ProtoReader(data);

      reader.readTag();
      final value = reader.readBytes();
      expect(value, Uint8List.fromList([0x01, 0x02, 0x03]));
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // Round-trip tests
  // ═══════════════════════════════════════════════════════════════════════════

  group('ProtoWriter/ProtoReader round-trip', () {
    test('varint round-trips correctly', () {
      final w = ProtoWriter();
      w.writeVarint(3, 12345);
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);
      final (fieldNumber, wireType) = r.readTag();
      expect(fieldNumber, 3);
      expect(wireType, 0);
      expect(r.readVarint(), 12345);
    });

    test('fixed32 round-trips correctly', () {
      final w = ProtoWriter();
      w.writeFixed32(2, 0xDEADBEEF);
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);
      final (fieldNumber, wireType) = r.readTag();
      expect(fieldNumber, 2);
      expect(wireType, 5);
      expect(r.readFixed32(), 0xDEADBEEF);
    });

    test('sfixed32 round-trips correctly for negative values', () {
      final w = ProtoWriter();
      w.writeSfixed32(1, -987654);
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);
      r.readTag();
      expect(r.readSfixed32(), -987654);
    });

    test('string round-trips correctly', () {
      final w = ProtoWriter();
      w.writeString(5, 'Meshtastic');
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);
      final (fieldNumber, wireType) = r.readTag();
      expect(fieldNumber, 5);
      expect(wireType, 2);
      expect(r.readString(), 'Meshtastic');
    });

    test('bool round-trips correctly', () {
      final w = ProtoWriter();
      w.writeBool(10, true);
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);
      final (fieldNumber, _) = r.readTag();
      expect(fieldNumber, 10);
      expect(r.readBool(), true);
    });

    test('multiple fields round-trip in order', () {
      final w = ProtoWriter();
      w.writeVarint(1, 42);
      w.writeString(2, 'test');
      w.writeFixed32(3, 0x12345678);
      final bytes = w.toBytes();

      final r = ProtoReader(bytes);

      var tag = r.readTag();
      expect(tag.$1, 1);
      expect(r.readVarint(), 42);

      tag = r.readTag();
      expect(tag.$1, 2);
      expect(r.readString(), 'test');

      tag = r.readTag();
      expect(tag.$1, 3);
      expect(r.readFixed32(), 0x12345678);

      expect(r.hasMore, false);
    });
  });

  // ═══════════════════════════════════════════════════════════════════════════
  // High-level message builder tests
  // ═══════════════════════════════════════════════════════════════════════════

  group('buildWantConfigMessage', () {
    test('produces non-empty bytes', () {
      final bytes = buildWantConfigMessage(42);
      expect(bytes.isNotEmpty, true);
    });

    test('has correct structure (field 3, varint wire type)', () {
      final bytes = buildWantConfigMessage(1);
      final r = ProtoReader(bytes);

      final (fieldNumber, wireType) = r.readTag();
      expect(fieldNumber, 3); // want_config_id is ToRadio field 3
      expect(wireType, 0); // varint
      expect(r.readVarint(), 1);
    });

    test('encodes config id value correctly', () {
      final bytes = buildWantConfigMessage(9999);
      final r = ProtoReader(bytes);
      r.readTag();
      expect(r.readVarint(), 9999);
    });
  });

  group('MqttClientProxyMessage', () {
    test('data payload round-trips with retained flag', () {
      final message = MqttClientProxyMessage(
        topic: 'msh/US/2/e/LongFast/!12345678',
        data: Uint8List.fromList([1, 2, 3, 4]),
        retained: true,
      );

      final parsed = MqttClientProxyMessage.fromBytes(message.toBytes());

      expect(parsed.topic, message.topic);
      expect(parsed.data, Uint8List.fromList([1, 2, 3, 4]));
      expect(parsed.text, isNull);
      expect(parsed.retained, true);
    });

    test('text payload round-trips', () {
      const message = MqttClientProxyMessage(
        topic: 'msh/US/2/json/LongFast/!12345678',
        text: '{"from":1}',
      );

      final parsed = MqttClientProxyMessage.fromBytes(message.toBytes());

      expect(parsed.topic, message.topic);
      expect(parsed.text, '{"from":1}');
      expect(parsed.data, isNull);
      expect(parsed.retained, false);
    });

    test('buildToRadioMqttClientProxyMessage uses ToRadio field 6', () {
      final bytes = buildToRadioMqttClientProxyMessage(
        MqttClientProxyMessage(
          topic: 'msh/US/2/e/LongFast/!12345678',
          data: Uint8List.fromList([9, 8, 7]),
        ),
      );
      final reader = ProtoReader(bytes);

      final (fieldNumber, wireType) = reader.readTag();
      expect(fieldNumber, 6);
      expect(wireType, 2);

      final parsed = MqttClientProxyMessage.fromBytes(reader.readBytes());
      expect(parsed.data, Uint8List.fromList([9, 8, 7]));
    });
  });

  group('Meshtastic MQTT proxy topics', () {
    test('subscribes to primary downlink channel and PKI', () {
      final state = MeshtasticDeviceState()
        ..mqttRootTopic = 'msh/US'
        ..channelName = 'LongFast'
        ..channelDownlinkEnabled = true;

      final topics = meshtasticMqttSubscriptionTopics(state);

      expect(topics, contains('msh/US/2/e/LongFast/+'));
      expect(topics, contains('msh/US/2/e/PKI/+'));
    });

    test('falls back to modem preset channel name when channel is empty', () {
      final state = MeshtasticDeviceState()
        ..mqttRootTopic = 'msh/US'
        ..modemPreset = ModemPreset.longModerate
        ..channelDownlinkEnabled = true;

      expect(
        meshtasticMqttSubscriptionTopics(state),
        contains('msh/US/2/e/LongMod/+'),
      );
    });
  });

  group('MQTT gateway profile policy', () {
    test('uses MQTT only for fixed gateway profiles', () {
      expect(
        meshtasticProfileUsesMqttGatewayBackhaul(MeshtasticProfile.pilot),
        false,
      );
      expect(
        meshtasticProfileUsesMqttGatewayBackhaul(MeshtasticProfile.driver),
        false,
      );
      expect(
        meshtasticProfileUsesMqttGatewayBackhaul(MeshtasticProfile.driverWifi),
        true,
      );
      expect(
        meshtasticProfileUsesMqttGatewayBackhaul(MeshtasticProfile.repeater),
        true,
      );
    });

    test('can disable radio MQTT and client proxy for app-relay trackers', () {
      final mqtt = _readSetMqttConfig(buildSetMqttConfig(
        enabled: false,
        address: '',
        username: '',
        password: '',
        rootTopic: 'msh',
        encryptionEnabled: false,
        tlsEnabled: false,
        proxyToClientEnabled: false,
      ));

      expect(mqtt[1], false); // enabled
      expect(mqtt[2], ''); // address
      expect(mqtt[3], ''); // username
      expect(mqtt[4], ''); // password
      expect(mqtt[5], false); // encryption_enabled
      expect(mqtt[7], false); // tls_enabled
      expect(mqtt[8], 'msh'); // root
      expect(mqtt[9], false); // proxy_to_client_enabled
    });

    test('keeps private MQTT enabled for fixed gateway profiles', () {
      final mqtt = _readSetMqttConfig(buildSetMqttConfig(
        enabled: true,
        address: 'mqtt-staging.aervyx.net',
        username: 'fleet',
        password: 'secret',
        rootTopic: 'msh/US',
        encryptionEnabled: false,
        tlsEnabled: true,
        proxyToClientEnabled: false,
      ));

      expect(mqtt[1], true);
      expect(mqtt[2], 'mqtt-staging.aervyx.net');
      expect(mqtt[3], 'fleet');
      expect(mqtt[4], 'secret');
      expect(mqtt[5], false);
      expect(mqtt[7], true);
      expect(mqtt[8], 'msh/US');
      expect(mqtt[9], false);
    });
  });

  group('buildPositionPacket', () {
    test('encodes lat/lon as sfixed32 (wire type 5)', () {
      final bytes = buildPositionPacket(
        to: 0xFFFFFFFF,
        from: 0x12345678,
        lat: 47.6062,
        lon: -122.3321,
        alt: 100.0,
        time: 1700000000,
      );

      expect(bytes.isNotEmpty, true);

      // Parse the outer MeshPacket to find the Data field
      final pktReader = ProtoReader(bytes);
      Uint8List? dataPayload;

      while (pktReader.hasMore) {
        final (fn, wt) = pktReader.readTag();
        if (fn == 4 && wt == 2) {
          // field 4 = decoded (Data message)
          final dataReader = pktReader.readMessageReader();
          while (dataReader.hasMore) {
            final (dfn, dwt) = dataReader.readTag();
            if (dfn == 2 && dwt == 2) {
              // field 2 = payload (Position bytes)
              dataPayload = dataReader.readBytes();
            } else {
              dataReader.skip(dwt);
            }
          }
        } else {
          pktReader.skip(wt);
        }
      }

      expect(dataPayload, isNotNull);

      // Parse the Position message inside the payload
      final posReader = ProtoReader(dataPayload!);
      int? latI;
      int? lonI;

      while (posReader.hasMore) {
        final (fn, wt) = posReader.readTag();
        if (fn == 1 && wt == 5) {
          latI = posReader.readSfixed32();
        } else if (fn == 2 && wt == 5) {
          lonI = posReader.readSfixed32();
        } else {
          posReader.skip(wt);
        }
      }

      // lat = 47.6062 * 1e7 = 476062000
      expect(latI, (47.6062 * 1e7).round());
      // lon = -122.3321 * 1e7 = -1223321000
      expect(lonI, (-122.3321 * 1e7).round());
    });

    test('position lat/lon survive round-trip for southern/western hemispheres',
        () {
      // Use a location in South America: Buenos Aires
      const lat = -34.6037;
      const lon = -58.3816;

      final bytes = buildPositionPacket(
        to: 0xFFFFFFFF,
        from: 0x00000001,
        lat: lat,
        lon: lon,
        alt: 25.0,
        time: 1700000000,
      );

      // Dig into MeshPacket → Data → Position payload
      final pktReader = ProtoReader(bytes);
      Uint8List? posPayload;

      while (pktReader.hasMore) {
        final (fn, wt) = pktReader.readTag();
        if (fn == 4 && wt == 2) {
          final dataReader = pktReader.readMessageReader();
          while (dataReader.hasMore) {
            final (dfn, dwt) = dataReader.readTag();
            if (dfn == 2 && dwt == 2) {
              posPayload = dataReader.readBytes();
            } else {
              dataReader.skip(dwt);
            }
          }
        } else {
          pktReader.skip(wt);
        }
      }

      expect(posPayload, isNotNull);

      final posReader = ProtoReader(posPayload!);
      int? latI;
      int? lonI;

      while (posReader.hasMore) {
        final (fn, wt) = posReader.readTag();
        if (fn == 1 && wt == 5) {
          latI = posReader.readSfixed32();
        } else if (fn == 2 && wt == 5) {
          lonI = posReader.readSfixed32();
        } else {
          posReader.skip(wt);
        }
      }

      // Verify negative values survive the round-trip
      expect(latI, isNotNull);
      expect(lonI, isNotNull);
      expect(latI!, lessThan(0));
      expect(lonI!, lessThan(0));

      // Convert back to decimal degrees and verify accuracy
      final recoveredLat = latI! / 1e7;
      final recoveredLon = lonI! / 1e7;
      expect(recoveredLat, closeTo(lat, 0.00001));
      expect(recoveredLon, closeTo(lon, 0.00001));
    });

    test('position lat/lon survive round-trip for northern/eastern hemispheres',
        () {
      // Sydney, Australia (southern, but eastern)
      const lat = 37.7749;
      const lon = 127.4194;

      final bytes = buildPositionPacket(
        to: 0xFFFFFFFF,
        from: 0x00000001,
        lat: lat,
        lon: lon,
        alt: 10.0,
        time: 1700000000,
      );

      final pktReader = ProtoReader(bytes);
      Uint8List? posPayload;

      while (pktReader.hasMore) {
        final (fn, wt) = pktReader.readTag();
        if (fn == 4 && wt == 2) {
          final dataReader = pktReader.readMessageReader();
          while (dataReader.hasMore) {
            final (dfn, dwt) = dataReader.readTag();
            if (dfn == 2 && dwt == 2) {
              posPayload = dataReader.readBytes();
            } else {
              dataReader.skip(dwt);
            }
          }
        } else {
          pktReader.skip(wt);
        }
      }

      expect(posPayload, isNotNull);

      final posReader = ProtoReader(posPayload!);
      int? latI;
      int? lonI;

      while (posReader.hasMore) {
        final (fn, wt) = posReader.readTag();
        if (fn == 1 && wt == 5) {
          latI = posReader.readSfixed32();
        } else if (fn == 2 && wt == 5) {
          lonI = posReader.readSfixed32();
        } else {
          posReader.skip(wt);
        }
      }

      expect(latI!, greaterThan(0));
      expect(lonI!, greaterThan(0));

      final recoveredLat = latI! / 1e7;
      final recoveredLon = lonI! / 1e7;
      expect(recoveredLat, closeTo(lat, 0.00001));
      expect(recoveredLon, closeTo(lon, 0.00001));
    });
  });
}

Map<int, Object?> _readSetMqttConfig(Uint8List bytes) {
  final admin = ProtoReader(bytes);
  Uint8List? moduleBytes;
  while (admin.hasMore) {
    final (field, wireType) = admin.readTag();
    if (field == 35 && wireType == 2) {
      moduleBytes = Uint8List.fromList(admin.readBytes());
    } else {
      admin.skip(wireType);
    }
  }

  final module = ProtoReader(moduleBytes!);
  Uint8List? mqttBytes;
  while (module.hasMore) {
    final (field, wireType) = module.readTag();
    if (field == 1 && wireType == 2) {
      mqttBytes = Uint8List.fromList(module.readBytes());
    } else {
      module.skip(wireType);
    }
  }

  final mqtt = ProtoReader(mqttBytes!);
  final values = <int, Object?>{};
  while (mqtt.hasMore) {
    final (field, wireType) = mqtt.readTag();
    switch (field) {
      case 1:
      case 5:
      case 7:
      case 9:
        values[field] = mqtt.readBool();
        break;
      case 2:
      case 3:
      case 4:
      case 8:
        values[field] = mqtt.readString();
        break;
      default:
        mqtt.skip(wireType);
    }
  }
  return values;
}
