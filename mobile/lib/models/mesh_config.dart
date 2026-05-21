class MeshConfig {
  final String? channelPsk;
  final String? mqttHost;
  final int mqttPort;
  final bool mqttTlsEnabled;
  final String? mqttUsername;
  final String? mqttPassword;
  final String topicPrefix;

  const MeshConfig({
    this.channelPsk,
    this.mqttHost,
    this.mqttPort = 1883,
    this.mqttTlsEnabled = false,
    this.mqttUsername,
    this.mqttPassword,
    this.topicPrefix = 'aervyx',
  });

  factory MeshConfig.fromJson(Map<String, dynamic> json) => MeshConfig(
        channelPsk: json['channel_psk'] as String?,
        mqttHost: json['mqtt_host'] as String?,
        mqttPort: json['mqtt_port'] as int? ?? 1883,
        mqttTlsEnabled: json['mqtt_tls_enabled'] as bool? ?? false,
        mqttUsername: json['mqtt_username'] as String?,
        mqttPassword: json['mqtt_password'] as String?,
        topicPrefix: json['topic_prefix'] as String? ?? 'aervyx',
      );
}
