import 'package:latlong2/latlong.dart';

class AirspaceSource {
  final int id;
  final bool enabled;

  const AirspaceSource({
    required this.id,
    required this.enabled,
  });

  factory AirspaceSource.fromJson(Map<String, dynamic> json) => AirspaceSource(
        id: json['id'] as int,
        enabled: json['enabled'] as bool? ?? true,
      );
}

class AirspaceRegion {
  final int id;
  final int sourceId;
  final String name;
  final String displayCategory;
  final String? lowerLimitLabel;
  final String? upperLimitLabel;
  final bool isRestrictedField;
  final List<LatLng> outerRing;
  final List<List<LatLng>> holes;
  final LatLng? labelPoint;

  const AirspaceRegion({
    required this.id,
    required this.sourceId,
    required this.name,
    required this.displayCategory,
    this.lowerLimitLabel,
    this.upperLimitLabel,
    required this.isRestrictedField,
    required this.outerRing,
    required this.holes,
    this.labelPoint,
  });

  factory AirspaceRegion.fromJson(Map<String, dynamic> json) {
    final geometry = json['geometry_json'] as Map<String, dynamic>? ?? {};
    final ringsJson = geometry['coordinates'] as List<dynamic>? ?? const [];
    final rings = ringsJson
        .map((ring) => _parseRing(ring as List<dynamic>? ?? const []))
        .where((ring) => ring.length >= 3)
        .toList();
    final labelLat = (json['label_latitude'] as num?)?.toDouble();
    final labelLon = (json['label_longitude'] as num?)?.toDouble();

    return AirspaceRegion(
      id: json['id'] as int,
      sourceId: json['source_id'] as int,
      name: json['name'] as String? ?? 'Airspace',
      displayCategory: json['display_category'] as String? ?? 'OTHER',
      lowerLimitLabel: json['lower_limit_label'] as String?,
      upperLimitLabel: json['upper_limit_label'] as String?,
      isRestrictedField: json['is_restricted_field'] as bool? ?? false,
      outerRing: rings.isNotEmpty ? rings.first : const [],
      holes: rings.length > 1 ? rings.skip(1).toList() : const [],
      labelPoint: labelLat != null && labelLon != null
          ? LatLng(labelLat, labelLon)
          : null,
    );
  }

  String get label {
    final lower = lowerLimitLabel ?? 'SFC';
    final upper = upperLimitLabel ?? 'UNL';
    return '$name\n$lower - $upper';
  }

  static List<LatLng> _parseRing(List<dynamic> ring) {
    return ring
        .map((coordinate) {
          if (coordinate is! List || coordinate.length < 2) return null;
          final lon = coordinate[0];
          final lat = coordinate[1];
          if (lon is! num || lat is! num) return null;
          return LatLng(lat.toDouble(), lon.toDouble());
        })
        .whereType<LatLng>()
        .toList();
  }
}
