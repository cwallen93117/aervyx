import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import '../models/meshtastic_protobufs.dart';

typedef ToRadioWriter = Future<void> Function(Uint8List data);

/// Bridges Meshtastic MQTT client-proxy messages between the radio and broker.
///
/// This follows Meshtastic's PhoneAPI path:
/// - FromRadio field 14 is published to MQTT.
/// - MQTT subscription messages are wrapped into ToRadio field 6.
class MqttClientProxyService {
  MqttServerClient? _client;
  StreamSubscription<List<MqttReceivedMessage<MqttMessage?>>?>? _updates;
  ToRadioWriter? _writeToRadio;
  final List<_RecentPublication> _recentPublications = [];

  bool get isRunning => _client != null;

  Future<void> start({
    required MeshtasticDeviceState deviceState,
    required ToRadioWriter writeToRadio,
  }) async {
    await stop();

    if (!deviceState.mqttEnabled || !deviceState.mqttProxyToClient) return;

    final endpoint = MqttBrokerEndpoint.fromDeviceState(deviceState);
    if (endpoint.host.isEmpty) return;

    _writeToRadio = writeToRadio;
    final clientId = _clientIdFor(deviceState);
    final client = MqttServerClient.withPort(
      endpoint.host,
      clientId,
      endpoint.port,
    );
    client.logging(on: false);
    client.setProtocolV311();
    client.keepAlivePeriod = 30;
    client.connectTimeoutPeriod = 5000;
    client.autoReconnect = true;
    client.resubscribeOnAutoReconnect = true;
    client.secure = endpoint.tls;
    client.connectionMessage = MqttConnectMessage()
        .withClientIdentifier(clientId)
        .startClean()
        .withWillQos(MqttQos.atLeastOnce);

    try {
      await client.connect(
        _emptyToNull(deviceState.mqttUsername),
        _emptyToNull(deviceState.mqttPassword),
      );
      if (client.connectionStatus?.state != MqttConnectionState.connected) {
        debugPrint('[MQTT proxy] connect failed: ${client.connectionStatus}');
        client.disconnect();
        return;
      }

      _client = client;
      _updates = client.updates?.listen(_handleBrokerMessages);
      for (final topic in meshtasticMqttSubscriptionTopics(deviceState)) {
        client.subscribe(topic, MqttQos.atLeastOnce);
      }
      debugPrint('[MQTT proxy] connected to ${endpoint.host}:${endpoint.port}');
    } catch (e) {
      debugPrint('[MQTT proxy] connect failed: $e');
      client.disconnect();
    }
  }

  Future<void> stop() async {
    await _updates?.cancel();
    _updates = null;
    final client = _client;
    _client = null;
    _writeToRadio = null;
    _recentPublications.clear();
    client?.disconnect();
  }

  void publishFromRadio(MqttClientProxyMessage message) {
    final client = _client;
    if (client == null || !message.hasPayload || message.topic.isEmpty) return;
    if (client.connectionStatus?.state != MqttConnectionState.connected) return;

    final payload = message.payloadBytes;
    final builder = MqttClientPayloadBuilder();
    for (final byte in payload) {
      builder.addByte(byte);
    }

    try {
      client.publishMessage(
        message.topic,
        MqttQos.atLeastOnce,
        builder.payload!,
        retain: message.retained,
      );
      _rememberPublished(message.topic, payload);
    } catch (e) {
      debugPrint('[MQTT proxy] publish failed: $e');
    }
  }

  void _handleBrokerMessages(
    List<MqttReceivedMessage<MqttMessage?>>? messages,
  ) {
    if (messages == null || messages.isEmpty) return;
    final writer = _writeToRadio;
    if (writer == null) return;

    for (final message in messages) {
      final payload = message.payload;
      if (payload is! MqttPublishMessage) continue;

      final bytes = Uint8List.fromList(payload.payload.message.toList());
      if (_wasRecentlyPublished(message.topic, bytes)) continue;

      final toRadio = buildToRadioMqttClientProxyMessage(
        MqttClientProxyMessage(
          topic: message.topic,
          data: bytes,
          retained: payload.header?.retain ?? false,
        ),
      );
      unawaited(writer(toRadio).catchError((Object e) {
        debugPrint('[MQTT proxy] write to radio failed: $e');
      }));
    }
  }

  void _rememberPublished(String topic, Uint8List payload) {
    _trimRecentPublications();
    _recentPublications.add(_RecentPublication(topic, payload, DateTime.now()));
  }

  bool _wasRecentlyPublished(String topic, Uint8List payload) {
    _trimRecentPublications();
    return _recentPublications.any(
      (p) => p.topic == topic && _bytesEqual(p.payload, payload),
    );
  }

  void _trimRecentPublications() {
    final cutoff = DateTime.now().subtract(const Duration(seconds: 30));
    _recentPublications.removeWhere((p) => p.createdAt.isBefore(cutoff));
    if (_recentPublications.length > 100) {
      _recentPublications.removeRange(
        0,
        _recentPublications.length - 100,
      );
    }
  }
}

class MqttBrokerEndpoint {
  final String host;
  final int port;
  final bool tls;

  const MqttBrokerEndpoint({
    required this.host,
    required this.port,
    required this.tls,
  });

  factory MqttBrokerEndpoint.fromDeviceState(MeshtasticDeviceState state) {
    final rawAddress = state.mqttAddress.trim().isEmpty
        ? _defaultPublicMqttServer
        : state.mqttAddress.trim();
    return MqttBrokerEndpoint.parse(
      rawAddress,
      tlsEnabled: state.mqttTlsEnabled ||
          _hostFromAddress(rawAddress).toLowerCase() ==
              _defaultPublicMqttServer,
    );
  }

  factory MqttBrokerEndpoint.parse(
    String rawAddress, {
    required bool tlsEnabled,
  }) {
    final parsed = _parseUriAddress(rawAddress);
    if (parsed != null) return parsed;

    final hostPort = rawAddress.split('/').first;
    final colonIndex = hostPort.lastIndexOf(':');
    var host = hostPort;
    int? port;
    if (colonIndex > -1 && colonIndex < hostPort.length - 1) {
      final parsedPort = int.tryParse(hostPort.substring(colonIndex + 1));
      if (parsedPort != null) {
        host = hostPort.substring(0, colonIndex);
        port = parsedPort;
      }
    }

    return MqttBrokerEndpoint(
      host: host,
      port: port ?? (tlsEnabled ? 8883 : 1883),
      tls: tlsEnabled,
    );
  }

  static MqttBrokerEndpoint? _parseUriAddress(String rawAddress) {
    if (!rawAddress.contains('://')) return null;
    final uri = Uri.tryParse(rawAddress);
    if (uri == null || uri.host.isEmpty) return null;
    final scheme = uri.scheme.toLowerCase();
    final tls = scheme == 'ssl' || scheme == 'mqtts' || scheme == 'tls';
    return MqttBrokerEndpoint(
      host: uri.host,
      port: uri.hasPort ? uri.port : (tls ? 8883 : 1883),
      tls: tls,
    );
  }
}

List<String> meshtasticMqttSubscriptionTopics(
  MeshtasticDeviceState state,
) {
  final root = state.mqttRootTopic.trim().isEmpty
      ? _defaultMqttRoot
      : state.mqttRootTopic.trim();
  final topics = <String>{'$root/2/e/PKI/+'};
  if (state.channelDownlinkEnabled) {
    topics.add('$root/2/e/${_channelNameFor(state)}/+');
  }
  return topics.toList(growable: false);
}

String _channelNameFor(MeshtasticDeviceState state) {
  if (state.channelName.trim().isNotEmpty) return state.channelName.trim();
  return switch (state.modemPreset) {
    ModemPreset.shortTurbo => 'ShortTurbo',
    ModemPreset.shortFast => 'ShortFast',
    ModemPreset.shortSlow => 'ShortSlow',
    ModemPreset.mediumFast => 'MediumFast',
    ModemPreset.mediumSlow => 'MediumSlow',
    ModemPreset.longFast => 'LongFast',
    ModemPreset.longSlow => 'LongSlow',
    ModemPreset.longModerate => 'LongMod',
    ModemPreset.veryLongSlow => 'VLongSlow',
    ModemPreset.longTurbo => 'LongTurbo',
  };
}

String _clientIdFor(MeshtasticDeviceState state) {
  final node = state.myNodeNum == 0
      ? 'unknown'
      : state.myNodeNum.toRadixString(16).padLeft(8, '0');
  final suffix = Random().nextInt(0xFFFF).toRadixString(16).padLeft(4, '0');
  return 'AervyxMqtt-$node-$suffix';
}

String? _emptyToNull(String value) {
  final trimmed = value.trim();
  return trimmed.isEmpty ? null : trimmed;
}

String _hostFromAddress(String rawAddress) {
  final uri = rawAddress.contains('://') ? Uri.tryParse(rawAddress) : null;
  if (uri != null && uri.host.isNotEmpty) return uri.host;
  return rawAddress.split('/').first.split(':').first;
}

bool _bytesEqual(Uint8List a, Uint8List b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i] != b[i]) return false;
  }
  return true;
}

class _RecentPublication {
  final String topic;
  final Uint8List payload;
  final DateTime createdAt;

  _RecentPublication(this.topic, this.payload, this.createdAt);
}

const _defaultPublicMqttServer = 'mqtt.meshtastic.org';
const _defaultMqttRoot = 'msh';
