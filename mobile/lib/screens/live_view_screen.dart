import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';
import '../services/tracking_service.dart';

/// A pilot position received from the live SSE stream.
class _LivePilot {
  final int pilotId;
  final double lat;
  final double lon;
  final double? alt;
  final double? speed;
  final String? aircraftIcon;
  final int? batteryLevel;
  DateTime lastSeen;

  _LivePilot({
    required this.pilotId,
    required this.lat,
    required this.lon,
    this.alt,
    this.speed,
    this.aircraftIcon,
    this.batteryLevel,
    DateTime? lastSeen,
  }) : lastSeen = lastSeen ?? DateTime.now();
}

/// Real-time map showing all pilots' positions for an active task.
/// Disabled during active flight recording to save battery.
class LiveViewScreen extends StatefulWidget {
  const LiveViewScreen({super.key});

  @override
  State<LiveViewScreen> createState() => _LiveViewScreenState();
}

class _LiveViewScreenState extends State<LiveViewScreen> {
  final Map<int, _LivePilot> _pilots = {};
  StreamSubscription<String>? _sseSubscription;
  String? _taskName;
  String? _error;
  bool _connected = false;

  @override
  void initState() {
    super.initState();
    _connectToLiveStream();
  }

  @override
  void dispose() {
    _sseSubscription?.cancel();
    super.dispose();
  }

  Future<void> _connectToLiveStream() async {
    final api = context.read<ApiService>();

    try {
      // First, get the active task
      final taskJson = await api.get(ApiConfig.activeTaskPath);
      if (!taskJson.containsKey('task_id')) {
        setState(() {
          _error = 'No active task found';
        });
        return;
      }

      final taskId = taskJson['task_id'];
      setState(() {
        _taskName = taskJson['task_name'] as String? ?? 'Task';
      });

      // Connect to SSE stream
      String? currentEvent;
      String dataBuffer = '';

      _sseSubscription = api.sseStream('/api/track/live/$taskId').listen(
        (line) {
          // Parse SSE format
          if (line.startsWith('event: ')) {
            currentEvent = line.substring(7).trim();
            dataBuffer = '';
          } else if (line.startsWith('data: ')) {
            dataBuffer += line.substring(6);
          } else if (line.startsWith(':')) {
            // Keepalive comment — ignore
            return;
          } else if (line.isEmpty && dataBuffer.isNotEmpty) {
            // End of message — process
            _processEvent(currentEvent, dataBuffer);
            currentEvent = null;
            dataBuffer = '';
          }

          // Also handle single-line data after event
          if (currentEvent != null && dataBuffer.isNotEmpty) {
            _processEvent(currentEvent, dataBuffer);
            currentEvent = null;
            dataBuffer = '';
          }
        },
        onError: (e) {
          if (!mounted) return;
          setState(() {
            _error = 'Connection lost: $e';
            _connected = false;
          });
          // Try to reconnect after 5 seconds
          Future.delayed(const Duration(seconds: 5), () {
            if (mounted) _connectToLiveStream();
          });
        },
        onDone: () {
          if (!mounted) return;
          setState(() {
            _connected = false;
          });
        },
      );

      if (!mounted) return;
      setState(() {
        _connected = true;
        _error = null;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Failed to connect: $e';
        _connected = false;
      });
    }
  }

  void _processEvent(String? event, String data) {
    if (!mounted) return;
    try {
      if (event == 'snapshot') {
        final list = jsonDecode(data) as List<dynamic>;
        setState(() {
          _pilots.clear();
          for (final item in list) {
            final pilot = _parsePilot(item as Map<String, dynamic>);
            _pilots[pilot.pilotId] = pilot;
          }
        });
      } else if (event == 'position') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilot = _parsePilot(json);
        setState(() {
          _pilots[pilot.pilotId] = pilot;
        });
      }
    } catch (_) {
      // Malformed SSE data — skip
    }
  }

  _LivePilot _parsePilot(Map<String, dynamic> json) {
    return _LivePilot(
      pilotId: json['pilot_id'] as int,
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      alt: (json['alt'] as num?)?.toDouble(),
      speed: (json['speed'] as num?)?.toDouble(),
      aircraftIcon: json['aircraft_icon'] as String?,
      batteryLevel: json['battery_level'] as int?,
    );
  }

  @override
  Widget build(BuildContext context) {
    final tracking = context.watch<TrackingService>();
    final theme = Theme.of(context);

    // Block if actively recording
    if (tracking.isInFlight) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live View')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.battery_saver,
                    size: 48, color: theme.colorScheme.error),
                const SizedBox(height: 16),
                Text(
                  'Live view disabled during recording',
                  style: theme.textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Stop recording to view live pilot positions.\nThis saves battery during your flight.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(_taskName ?? 'Live View'),
        actions: [
          // Connection indicator
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Icon(
              Icons.circle,
              size: 12,
              color: _connected ? Colors.green : Colors.red,
            ),
          ),
        ],
      ),
      body: _error != null && _pilots.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.cloud_off,
                        size: 48, color: theme.colorScheme.error),
                    const SizedBox(height: 16),
                    Text(_error!,
                        style: theme.textTheme.bodyMedium,
                        textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: _connectToLiveStream,
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            )
          : Stack(
              children: [
                FlutterMap(
                  options: MapOptions(
                    initialCenter: _pilots.isNotEmpty
                        ? LatLng(
                            _pilots.values.first.lat,
                            _pilots.values.first.lon,
                          )
                        : const LatLng(46.0, 11.0), // Default: Alps
                    initialZoom: 12,
                  ),
                  children: [
                    TileLayer(
                      urlTemplate:
                          'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'com.aervyx.aervyx_mobile',
                    ),
                    // Pilot markers
                    MarkerLayer(
                      markers: _pilots.values.map((pilot) {
                        return Marker(
                          point: LatLng(pilot.lat, pilot.lon),
                          width: 40,
                          height: 40,
                          child: _PilotMarker(pilot: pilot),
                        );
                      }).toList(),
                    ),
                  ],
                ),
                // Pilot count chip
                Positioned(
                  top: 12,
                  left: 12,
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.surface.withAlpha(230),
                      borderRadius: BorderRadius.circular(20),
                      boxShadow: [
                        BoxShadow(
                            color: Colors.black.withAlpha(30), blurRadius: 4),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.people, size: 16,
                            color: theme.colorScheme.primary),
                        const SizedBox(width: 6),
                        Text(
                          '${_pilots.length} pilot${_pilots.length == 1 ? '' : 's'}',
                          style: theme.textTheme.labelMedium,
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}

class _PilotMarker extends StatelessWidget {
  final _LivePilot pilot;

  const _PilotMarker({required this.pilot});

  IconData _iconForAircraft(String? type) {
    switch (type) {
      case 'hang_glider':
        return Icons.air;
      case 'sailplane':
        return Icons.flight;
      case 'paraglider':
      default:
        return Icons.paragliding;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: Colors.blue, width: 2),
            boxShadow: [
              BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 3),
            ],
          ),
          child: Icon(
            _iconForAircraft(pilot.aircraftIcon),
            size: 18,
            color: Colors.blue,
          ),
        ),
        Text(
          '#${pilot.pilotId}',
          style: const TextStyle(
            fontSize: 9,
            fontWeight: FontWeight.bold,
            color: Colors.black87,
          ),
        ),
      ],
    );
  }
}
