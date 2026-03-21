class TaskPoint {
  final int id;
  final int position;
  final String pointType;
  final double radiusM;
  final String name;
  final double latitude;
  final double longitude;

  const TaskPoint({
    required this.id,
    required this.position,
    required this.pointType,
    required this.radiusM,
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  factory TaskPoint.fromJson(Map<String, dynamic> json) => TaskPoint(
        id: json['id'] as int,
        position: json['position'] as int,
        pointType: json['point_type'] as String,
        radiusM: (json['radius_m'] as num).toDouble(),
        name: json['name'] as String,
        latitude: (json['latitude'] as num).toDouble(),
        longitude: (json['longitude'] as num).toDouble(),
      );
}

class Task {
  final int id;
  final int eventId;
  final String name;
  final String status;
  final String taskType;
  final List<TaskPoint> points;

  const Task({
    required this.id,
    required this.eventId,
    required this.name,
    required this.status,
    required this.taskType,
    required this.points,
  });

  factory Task.fromJson(Map<String, dynamic> json) => Task(
        id: json['id'] as int,
        eventId: json['event_id'] as int,
        name: json['name'] as String,
        status: json['status'] as String,
        taskType: json['task_type'] as String,
        points: (json['points'] as List<dynamic>)
            .map((p) => TaskPoint.fromJson(p as Map<String, dynamic>))
            .toList(),
      );
}

class Event {
  final int id;
  final String name;
  final String location;
  final String startsOn;
  final String endsOn;

  const Event({
    required this.id,
    required this.name,
    required this.location,
    required this.startsOn,
    required this.endsOn,
  });

  factory Event.fromJson(Map<String, dynamic> json) => Event(
        id: json['id'] as int,
        name: json['name'] as String,
        location: json['location'] as String,
        startsOn: json['starts_on'] as String,
        endsOn: json['ends_on'] as String,
      );
}
