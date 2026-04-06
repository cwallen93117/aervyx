import 'package:latlong2/latlong.dart';

import '../utils/polyline.dart';

/// A single stop on the driver's pickup route.
class RouteStop {
  final int pilotId;
  final String pilotName;
  final int landingId;
  final double lat;
  final double lon;
  final DateTime landedAt;
  final DateTime readyAt;
  final DateTime eta;
  final double distanceKm;
  final String status; // landed | ready | picked_up

  RouteStop({
    required this.pilotId,
    required this.pilotName,
    required this.landingId,
    required this.lat,
    required this.lon,
    required this.landedAt,
    required this.readyAt,
    required this.eta,
    required this.distanceKm,
    required this.status,
  });

  factory RouteStop.fromJson(Map<String, dynamic> json) {
    return RouteStop(
      pilotId: json['pilot_id'] as int,
      pilotName: json['pilot_name'] as String,
      landingId: json['landing_id'] as int,
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      landedAt: DateTime.parse(json['landed_at'] as String),
      readyAt: DateTime.parse(json['ready_at'] as String),
      eta: DateTime.parse(json['eta'] as String),
      distanceKm: (json['distance_km'] as num).toDouble(),
      status: json['status'] as String,
    );
  }

  /// Minutes until pilot is ready for pickup.
  int get minutesUntilReady {
    final diff = readyAt.difference(DateTime.now().toUtc()).inMinutes;
    return diff > 0 ? diff : 0;
  }

  bool get isReady => DateTime.now().toUtc().isAfter(readyAt);
}

/// A single turn-by-turn maneuver instruction.
class RouteManeuver {
  final String instruction;
  final double distanceKm;
  final int timeSeconds;
  final int type;
  final String? streetName;
  final int beginShapeIndex;
  final int endShapeIndex;

  RouteManeuver({
    required this.instruction,
    required this.distanceKm,
    required this.timeSeconds,
    required this.type,
    this.streetName,
    required this.beginShapeIndex,
    required this.endShapeIndex,
  });

  factory RouteManeuver.fromJson(Map<String, dynamic> json) {
    return RouteManeuver(
      instruction: json['instruction'] as String,
      distanceKm: (json['distance_km'] as num).toDouble(),
      timeSeconds: json['time_seconds'] as int,
      type: json['type'] as int,
      streetName: json['street_name'] as String?,
      beginShapeIndex: json['begin_shape_index'] as int,
      endShapeIndex: json['end_shape_index'] as int,
    );
  }
}

/// One leg of the route (driver to stop, or stop to stop).
class RouteLeg {
  final int pilotId;
  final List<RouteManeuver> maneuvers;
  final double distanceKm;
  final int timeSeconds;
  final String shapeEncoded;
  late final List<LatLng> shape;

  RouteLeg({
    required this.pilotId,
    required this.maneuvers,
    required this.distanceKm,
    required this.timeSeconds,
    required this.shapeEncoded,
  }) {
    shape = shapeEncoded.isNotEmpty
        ? decodePolyline6(shapeEncoded)
        : <LatLng>[];
  }

  factory RouteLeg.fromJson(Map<String, dynamic> json) {
    return RouteLeg(
      pilotId: json['pilot_id'] as int,
      maneuvers: (json['maneuvers'] as List<dynamic>)
          .map((m) => RouteManeuver.fromJson(m as Map<String, dynamic>))
          .toList(),
      distanceKm: (json['distance_km'] as num).toDouble(),
      timeSeconds: json['time_seconds'] as int,
      shapeEncoded: json['shape'] as String? ?? '',
    );
  }
}

/// The complete driver route response.
class DriverRoute {
  final List<RouteStop> stops;
  final List<RouteLeg> legs;
  final double totalDistanceKm;
  final int totalTimeSeconds;
  final String shapeEncoded;
  late final List<LatLng> shape;

  DriverRoute({
    required this.stops,
    required this.legs,
    required this.totalDistanceKm,
    required this.totalTimeSeconds,
    required this.shapeEncoded,
  }) {
    shape = shapeEncoded.isNotEmpty
        ? decodePolyline6(shapeEncoded)
        : <LatLng>[];
  }

  factory DriverRoute.fromJson(Map<String, dynamic> json) {
    return DriverRoute(
      stops: (json['stops'] as List<dynamic>)
          .map((s) => RouteStop.fromJson(s as Map<String, dynamic>))
          .toList(),
      legs: (json['legs'] as List<dynamic>)
          .map((l) => RouteLeg.fromJson(l as Map<String, dynamic>))
          .toList(),
      totalDistanceKm: (json['total_distance_km'] as num).toDouble(),
      totalTimeSeconds: json['total_time_seconds'] as int,
      shapeEncoded: json['shape'] as String? ?? '',
    );
  }

  /// Human-readable total time.
  String get totalTimeFormatted {
    final h = totalTimeSeconds ~/ 3600;
    final m = (totalTimeSeconds % 3600) ~/ 60;
    if (h > 0) return '${h}h ${m}m';
    return '${m}m';
  }
}
