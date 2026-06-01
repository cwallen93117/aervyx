import 'package:aervyx_mobile/models/airspace.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('AirspaceRegion parses GeoJSON polygon rings', () {
    final region = AirspaceRegion.fromJson({
      'id': 12,
      'source_id': 4,
      'name': 'Restricted Area',
      'display_category': 'R',
      'lower_limit_label': 'SFC',
      'upper_limit_label': '4500 FT',
      'is_restricted_field': false,
      'label_latitude': 35.5,
      'label_longitude': -82.5,
      'geometry_json': {
        'type': 'Polygon',
        'coordinates': [
          [
            [-82.0, 35.0],
            [-82.1, 35.0],
            [-82.1, 35.1],
            [-82.0, 35.0],
          ],
        ],
      },
    });

    expect(region.sourceId, 4);
    expect(region.outerRing, hasLength(4));
    expect(region.outerRing.first.latitude, 35.0);
    expect(region.outerRing.first.longitude, -82.0);
    expect(region.label, 'Restricted Area\nSFC - 4500 FT');
  });
}
