class MeshConfig {
  final String? channelPsk;
  final String? mqttHost;
  final int mqttPort;
  final String topicPrefix;

  const MeshConfig({
    this.channelPsk,
    this.mqttHost,
    this.mqttPort = 1883,
    this.topicPrefix = 'aervyx',
  });

  factory MeshConfig.fromJson(Map<String, dynamic> json) => MeshConfig(
        channelPsk: json['channel_psk'] as String?,
        mqttHost: json['mqtt_host'] as String?,
        mqttPort: json['mqtt_port'] as int? ?? 1883,
        topicPrefix: json['topic_prefix'] as String? ?? 'aervyx',
      );
}
