import 'dart:math';

/// A competition course point (start, turnpoint, goal, etc.).
class Turnpoint {
  final String id;
  final String name;
  final String type; // 'start', 'turnpoint', 'goal', 'ess'
  final double lat;
  final double lon;
  final double radiusMeters; // cylinder radius

  const Turnpoint({
    required this.id,
    required this.name,
    required this.type,
    required this.lat,
    required this.lon,
    required this.radiusMeters,
  });

  factory Turnpoint.fromJson(Map<String, dynamic> json) => Turnpoint(
        id: json['id'] as String,
        name: json['name'] as String,
        type: json['type'] as String? ?? 'turnpoint',
        lat: (json['lat'] as num).toDouble(),
        lon: (json['lon'] as num).toDouble(),
        radiusMeters: (json['radius'] as num?)?.toDouble() ?? 400.0,
      );

  /// Haversine distance in metres from this turnpoint to [lat2], [lon2].
  double distanceTo(double lat2, double lon2) {
    const earthRadius = 6371000.0; // metres
    final dLat = _toRad(lat2 - lat);
    final dLon = _toRad(lon2 - lon);
    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_toRad(lat)) * cos(_toRad(lat2)) * sin(dLon / 2) * sin(dLon / 2);
    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  static double _toRad(double deg) => deg * pi / 180;
}

/// Active task info returned by the backend.
class ActiveTask {
  final int taskId;
  final int? eventId;
  final String taskName;
  final List<String> visibleAirspaceClasses;
  final bool showRestrictedFields;
  final List<Turnpoint> turnpoints;

  const ActiveTask({
    required this.taskId,
    this.eventId,
    required this.taskName,
    this.visibleAirspaceClasses = const [
      'B',
      'C',
      'D',
      'P',
      'Q',
      'R',
      'TFR',
      'OTHER'
    ],
    this.showRestrictedFields = true,
    required this.turnpoints,
  });

  factory ActiveTask.fromJson(Map<String, dynamic> json) => ActiveTask(
        taskId: json['task_id'] as int,
        eventId: json['event_id'] as int?,
        taskName: json['task_name'] as String? ?? 'Task',
        visibleAirspaceClasses:
            (json['visible_airspace_classes'] as List<dynamic>?)
                    ?.map((item) => item.toString())
                    .toList() ??
                const ['B', 'C', 'D', 'P', 'Q', 'R', 'TFR', 'OTHER'],
        showRestrictedFields: json['show_restricted_fields'] as bool? ?? true,
        turnpoints: (json['turnpoints'] as List<dynamic>)
            .map((tp) => Turnpoint.fromJson(tp as Map<String, dynamic>))
            .toList(),
      );
}
