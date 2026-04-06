import 'package:latlong2/latlong.dart';

/// Decode a Valhalla-style encoded polyline (precision 6).
///
/// Valhalla uses precision 6 (divide by 1e6) rather than the
/// Google standard precision 5 (divide by 1e5).
List<LatLng> decodePolyline6(String encoded) {
  final points = <LatLng>[];
  int index = 0;
  int lat = 0;
  int lon = 0;

  while (index < encoded.length) {
    int shift = 0;
    int result = 0;
    int b;
    do {
      b = encoded.codeUnitAt(index++) - 63;
      result |= (b & 0x1F) << shift;
      shift += 5;
    } while (b >= 0x20);
    lat += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);

    shift = 0;
    result = 0;
    do {
      b = encoded.codeUnitAt(index++) - 63;
      result |= (b & 0x1F) << shift;
      shift += 5;
    } while (b >= 0x20);
    lon += (result & 1) != 0 ? ~(result >> 1) : (result >> 1);

    points.add(LatLng(lat / 1e6, lon / 1e6));
  }

  return points;
}
