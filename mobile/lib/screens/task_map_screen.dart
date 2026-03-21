import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../models/position.dart' as model;
import '../models/task.dart';
import '../services/tracking_service.dart';
import '../widgets/tracking_controls.dart';

class TaskMapScreen extends StatefulWidget {
  final Task task;
  const TaskMapScreen({super.key, required this.task});

  @override
  State<TaskMapScreen> createState() => _TaskMapScreenState();
}

class _TaskMapScreenState extends State<TaskMapScreen> {
  final MapController _mapCtl = MapController();
  List<model.Position> _livePositions = [];
  StreamSubscription<List<model.Position>>? _sseSub;

  @override
  void initState() {
    super.initState();
    _connectLiveStream();
  }

  void _connectLiveStream() {
    final tracking = context.read<TrackingService>();
    _sseSub = tracking.livePositionStream(widget.task.id).listen((positions) {
      if (mounted) setState(() => _livePositions = positions);
    }, onError: (_) {
      // Silently ignore SSE errors — will reconnect on next screen visit
    });
  }

  @override
  void dispose() {
    _sseSub?.cancel();
    _mapCtl.dispose();
    super.dispose();
  }

  LatLng _taskCenter() {
    if (widget.task.points.isEmpty) return const LatLng(47.0, 11.0);
    final lats = widget.task.points.map((p) => p.latitude);
    final lons = widget.task.points.map((p) => p.longitude);
    return LatLng(
      lats.reduce((a, b) => a + b) / lats.length,
      lons.reduce((a, b) => a + b) / lons.length,
    );
  }

  LatLngBounds? _taskBounds() {
    if (widget.task.points.isEmpty) return null;
    final lats = widget.task.points.map((p) => p.latitude).toList();
    final lons = widget.task.points.map((p) => p.longitude).toList();
    lats.sort();
    lons.sort();
    return LatLngBounds(
      LatLng(lats.first - 0.01, lons.first - 0.01),
      LatLng(lats.last + 0.01, lons.last + 0.01),
    );
  }

  @override
  Widget build(BuildContext context) {
    final turnpointMarkers = widget.task.points.map((tp) {
      return Marker(
        point: LatLng(tp.latitude, tp.longitude),
        width: 40,
        height: 40,
        child: Tooltip(
          message: '${tp.name} (${tp.pointType})',
          child: Icon(
            tp.pointType == 'start'
                ? Icons.play_circle
                : tp.pointType == 'goal'
                    ? Icons.flag_circle
                    : Icons.circle_outlined,
            color: tp.pointType == 'start'
                ? Colors.green
                : tp.pointType == 'goal'
                    ? Colors.red
                    : Colors.blue,
            size: 28,
          ),
        ),
      );
    }).toList();

    final turnpointCircles = widget.task.points.map((tp) {
      return CircleMarker(
        point: LatLng(tp.latitude, tp.longitude),
        radius: tp.radiusM,
        useRadiusInMeter: true,
        color: Colors.blue.withValues(alpha: 0.08),
        borderColor: Colors.blue.withValues(alpha: 0.4),
        borderStrokeWidth: 1.5,
      );
    }).toList();

    final coursePolyline = Polyline(
      points: widget.task.points
          .map((tp) => LatLng(tp.latitude, tp.longitude))
          .toList(),
      color: Colors.blueGrey,
      strokeWidth: 2,
    );

    // Live pilot markers
    final pilotMarkers = _livePositions.map((pos) {
      return Marker(
        point: LatLng(pos.lat, pos.lon),
        width: 36,
        height: 36,
        child: Tooltip(
          message:
              'Pilot ${pos.pilotId ?? "?"} · ${pos.alt?.toStringAsFixed(0) ?? "-"}m',
          child: const Icon(Icons.paragliding, color: Colors.deepOrange, size: 28),
        ),
      );
    }).toList();

    final bounds = _taskBounds();

    return Scaffold(
      appBar: AppBar(title: Text(widget.task.name)),
      body: Column(
        children: [
          Expanded(
            child: FlutterMap(
              mapController: _mapCtl,
              options: MapOptions(
                initialCenter: _taskCenter(),
                initialZoom: 12,
                initialCameraFit: bounds != null
                    ? CameraFit.bounds(
                        bounds: bounds,
                        padding: const EdgeInsets.all(48),
                      )
                    : null,
              ),
              children: [
                TileLayer(
                  urlTemplate:
                      'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                  userAgentPackageName: 'com.aervyx.mobile',
                ),
                CircleLayer(circles: turnpointCircles),
                PolylineLayer(polylines: [coursePolyline]),
                MarkerLayer(markers: [...turnpointMarkers, ...pilotMarkers]),
              ],
            ),
          ),
          TrackingControls(taskId: widget.task.id),
        ],
      ),
    );
  }
}
