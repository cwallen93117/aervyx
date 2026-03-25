class Position {
  final String id;
  final int? pilotId;
  final int taskId;
  final double lat;
  final double lon;
  final double? alt;
  final double? speed;
  final double? heading;
  final double? accuracy;
  final DateTime timestamp;
  final String? source;
  final String? deviceId;
  final int? batteryLevel;

  const Position({
    required this.id,
    this.pilotId,
    required this.taskId,
    required this.lat,
    required this.lon,
    this.alt,
    this.speed,
    this.heading,
    this.accuracy,
    required this.timestamp,
    this.source,
    this.deviceId,
    this.batteryLevel,
  });

  factory Position.fromJson(Map<String, dynamic> json) => Position(
        id: json['id'] as String,
        pilotId: json['pilot_id'] as int?,
        taskId: json['task_id'] as int,
        lat: (json['lat'] as num).toDouble(),
        lon: (json['lon'] as num).toDouble(),
        alt: (json['alt'] as num?)?.toDouble(),
        speed: (json['speed'] as num?)?.toDouble(),
        heading: (json['heading'] as num?)?.toDouble(),
        accuracy: (json['accuracy'] as num?)?.toDouble(),
        timestamp: DateTime.parse(json['timestamp'] as String),
        source: json['source'] as String?,
        deviceId: json['device_id'] as String?,
        batteryLevel: json['battery_level'] as int?,
      );

  Map<String, dynamic> toJson() => {
        'task_id': taskId,
        'lat': lat,
        'lon': lon,
        if (alt != null) 'alt': alt,
        if (speed != null) 'speed': speed,
        if (heading != null) 'heading': heading,
        if (accuracy != null) 'accuracy': accuracy,
        'timestamp': timestamp.toUtc().toIso8601String(),
        if (source != null) 'source': source,
        if (deviceId != null) 'device_id': deviceId,
        if (batteryLevel != null) 'battery_level': batteryLevel,
      };
}
