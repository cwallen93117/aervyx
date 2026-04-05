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
  _MapStyle _mapStyle = _MapStyle.map;

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
              urlTemplate: _mapStyle.urlTemplate,
              userAgentPackageName: 'com.aervyx.aervyx_mobile',
              maxZoom: _mapStyle.maxZoom,
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
        // Map style selector
        Positioned(
          top: 12,
          right: 12,
          child: _MapStyleSelector(
            current: _mapStyle,
            onChanged: (style) => setState(() => _mapStyle = style),
          ),
        ),
        // Altitude legend — above the info bar (accounts for nav bar inset)
        if (_minAlt != null && _maxAlt != null)
          Positioned(
            right: 12,
            bottom: 56 + MediaQuery.of(context).padding.bottom,
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
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withAlpha(220),
        borderRadius: BorderRadius.circular(8),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 4),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // Altitude labels and gradient bar
          Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('${maxAlt.toStringAsFixed(0)}m',
                  style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w600)),
              const SizedBox(height: 2),
              Container(
                width: 12,
                height: 64,
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
                  borderRadius: BorderRadius.all(Radius.circular(3)),
                ),
              ),
              const SizedBox(height: 2),
              Text('${minAlt.toStringAsFixed(0)}m',
                  style: const TextStyle(fontSize: 9, fontWeight: FontWeight.w600)),
            ],
          ),
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

// ── Map Style ──

enum _MapStyle {
  map(
    label: 'Map',
    icon: Icons.map_outlined,
    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    maxZoom: 19,
  ),
  satellite(
    label: 'Satellite',
    icon: Icons.satellite_alt,
    urlTemplate: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    maxZoom: 18,
  ),
  terrain(
    label: 'Terrain',
    icon: Icons.terrain,
    urlTemplate: 'https://tile.opentopomap.org/{z}/{x}/{y}.png',
    maxZoom: 17,
  );

  const _MapStyle({
    required this.label,
    required this.icon,
    required this.urlTemplate,
    required this.maxZoom,
  });

  final String label;
  final IconData icon;
  final String urlTemplate;
  final double maxZoom;
}

class _MapStyleSelector extends StatelessWidget {
  final _MapStyle current;
  final ValueChanged<_MapStyle> onChanged;

  const _MapStyleSelector({required this.current, required this.onChanged});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white.withAlpha(220),
        borderRadius: BorderRadius.circular(8),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 4),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: _MapStyle.values.map((style) {
          final selected = style == current;
          return InkWell(
            onTap: () => onChanged(style),
            borderRadius: BorderRadius.circular(8),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
              decoration: BoxDecoration(
                color: selected ? Colors.blue.withAlpha(30) : Colors.transparent,
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    style.icon,
                    size: 16,
                    color: selected ? Colors.blue : Colors.grey.shade600,
                  ),
                  const SizedBox(width: 4),
                  Text(
                    style.label,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                      color: selected ? Colors.blue : Colors.grey.shade700,
                    ),
                  ),
                ],
              ),
            ),
          );
        }).toList(),
      ),
    );
  }
}
