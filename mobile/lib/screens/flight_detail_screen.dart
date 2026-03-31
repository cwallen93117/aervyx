import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../services/igc_service.dart';

/// Displays a saved flight track on a map with altitude gradient coloring.
class FlightDetailScreen extends StatefulWidget {
  final SavedFlight flight;

  const FlightDetailScreen({super.key, required this.flight});

  @override
  State<FlightDetailScreen> createState() => _FlightDetailScreenState();
}

class _FlightDetailScreenState extends State<FlightDetailScreen> {
  List<_TrackSegment>? _segments;
  LatLng? _takeoff;
  LatLng? _landing;
  LatLngBounds? _bounds;
  double? _minAlt;
  double? _maxAlt;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadTrack();
  }

  Future<void> _loadTrack() async {
    try {
      final points = await IgcService.parseFullTrack(widget.flight.filePath);
      if (points.isEmpty) {
        setState(() {
          _error = 'No track points found';
          _loading = false;
        });
        return;
      }

      // Find altitude range
      double minAlt = points.first.gpsAlt;
      double maxAlt = points.first.gpsAlt;
      for (final p in points) {
        if (p.gpsAlt < minAlt) minAlt = p.gpsAlt;
        if (p.gpsAlt > maxAlt) maxAlt = p.gpsAlt;
      }

      // Build segments colored by altitude
      final segments = <_TrackSegment>[];
      for (int i = 0; i < points.length - 1; i++) {
        final p1 = points[i];
        final p2 = points[i + 1];
        final avgAlt = (p1.gpsAlt + p2.gpsAlt) / 2;
        segments.add(_TrackSegment(
          start: LatLng(p1.lat, p1.lon),
          end: LatLng(p2.lat, p2.lon),
          color: _altitudeColor(avgAlt, minAlt, maxAlt),
        ));
      }

      // Takeoff and landing markers
      final takeoff = LatLng(points.first.lat, points.first.lon);
      final landing = LatLng(points.last.lat, points.last.lon);

      // Calculate bounds
      double minLat = points.first.lat, maxLat = points.first.lat;
      double minLon = points.first.lon, maxLon = points.first.lon;
      for (final p in points) {
        if (p.lat < minLat) minLat = p.lat;
        if (p.lat > maxLat) maxLat = p.lat;
        if (p.lon < minLon) minLon = p.lon;
        if (p.lon > maxLon) maxLon = p.lon;
      }

      setState(() {
        _segments = segments;
        _takeoff = takeoff;
        _landing = landing;
        _minAlt = minAlt;
        _maxAlt = maxAlt;
        _bounds = LatLngBounds(
          LatLng(minLat - 0.005, minLon - 0.005),
          LatLng(maxLat + 0.005, maxLon + 0.005),
        );
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Failed to load track: $e';
        _loading = false;
      });
    }
  }

  /// Map altitude value to a color gradient: blue (low) → green → yellow → red (high)
  static Color _altitudeColor(double alt, double minAlt, double maxAlt) {
    if (maxAlt <= minAlt) return Colors.blue;
    final t = ((alt - minAlt) / (maxAlt - minAlt)).clamp(0.0, 1.0);

    if (t < 0.25) {
      return Color.lerp(Colors.blue, Colors.green, t / 0.25)!;
    } else if (t < 0.5) {
      return Color.lerp(Colors.green, Colors.yellow, (t - 0.25) / 0.25)!;
    } else if (t < 0.75) {
      return Color.lerp(Colors.yellow, Colors.orange, (t - 0.5) / 0.25)!;
    } else {
      return Color.lerp(Colors.orange, Colors.red, (t - 0.75) / 0.25)!;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.flight.filename.replaceAll('.igc', ''),
          style: const TextStyle(fontSize: 16),
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(_error!,
                        style: TextStyle(color: theme.colorScheme.error)),
                  ),
                )
              : _buildMap(theme),
    );
  }

  Widget _buildMap(ThemeData theme) {
    return Stack(
      children: [
        FlutterMap(
          options: MapOptions(
            initialCameraFit: _bounds != null
                ? CameraFit.bounds(
                    bounds: _bounds!,
                    padding: const EdgeInsets.all(40),
                  )
                : null,
          ),
          children: [
            TileLayer(
              urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
              userAgentPackageName: 'com.aervyx.aervyx_mobile',
            ),
            // Flight track segments (altitude-colored)
            if (_segments != null)
              PolylineLayer(
                polylines: _segments!
                    .map((seg) => Polyline(
                          points: [seg.start, seg.end],
                          color: seg.color,
                          strokeWidth: 3.0,
                        ))
                    .toList(),
              ),
            // Takeoff and landing markers
            if (_takeoff != null && _landing != null)
              MarkerLayer(
                markers: [
                  Marker(
                    point: _takeoff!,
                    width: 32,
                    height: 32,
                    child: const Icon(Icons.flight_takeoff,
                        color: Colors.green, size: 28),
                  ),
                  Marker(
                    point: _landing!,
                    width: 32,
                    height: 32,
                    child: const Icon(Icons.flight_land,
                        color: Colors.red, size: 28),
                  ),
                ],
              ),
          ],
        ),
        // Altitude legend
        if (_minAlt != null && _maxAlt != null)
          Positioned(
            right: 12,
            bottom: 12,
            child: _AltitudeLegend(minAlt: _minAlt!, maxAlt: _maxAlt!),
          ),
        // Flight info bar
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: _FlightInfoBar(flight: widget.flight),
        ),
      ],
    );
  }
}

class _TrackSegment {
  final LatLng start;
  final LatLng end;
  final Color color;

  const _TrackSegment({
    required this.start,
    required this.end,
    required this.color,
  });
}

class _AltitudeLegend extends StatelessWidget {
  final double minAlt;
  final double maxAlt;

  const _AltitudeLegend({required this.minAlt, required this.maxAlt});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: Colors.white.withAlpha(220),
        borderRadius: BorderRadius.circular(8),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 4),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Altitude',
              style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Container(
            width: 16,
            height: 80,
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  Colors.red,
                  Colors.orange,
                  Colors.yellow,
                  Colors.green,
                  Colors.blue,
                ],
              ),
              borderRadius: BorderRadius.all(Radius.circular(4)),
            ),
          ),
          const SizedBox(height: 2),
          Text('${maxAlt.toStringAsFixed(0)}m',
              style: const TextStyle(fontSize: 9)),
          const SizedBox(height: 50),
          Text('${minAlt.toStringAsFixed(0)}m',
              style: const TextStyle(fontSize: 9)),
        ],
      ),
    );
  }
}

class _FlightInfoBar extends StatelessWidget {
  final SavedFlight flight;

  const _FlightInfoBar({required this.flight});

  String _formatDuration(Duration d) {
    if (d.inHours > 0) {
      return '${d.inHours}h ${d.inMinutes % 60}m';
    }
    return '${d.inMinutes}m';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.white.withAlpha(230),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: SafeArea(
        top: false,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
          children: [
            _InfoChip(
                icon: Icons.timer,
                label: _formatDuration(flight.duration)),
            _InfoChip(
                icon: Icons.height,
                label: flight.maxAltitude != null
                    ? '${flight.maxAltitude!.toStringAsFixed(0)}m max'
                    : '--'),
            _InfoChip(
                icon: Icons.speed,
                label: flight.maxSpeed != null
                    ? '${(flight.maxSpeed! * 3.6).toStringAsFixed(0)} km/h'
                    : '--'),
            _InfoChip(
                icon: Icons.location_on,
                label: '${flight.trackPoints} pts'),
          ],
        ),
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _InfoChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: Colors.grey.shade700),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 12)),
      ],
    );
  }
}
