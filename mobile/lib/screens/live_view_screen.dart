import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/tracking_service.dart';
import '../widgets/live_map_style.dart';
import '../widgets/map_scale_bar.dart';

/// A pilot position received from the backend.
class _LivePilot {
  final String subjectKey;
  final int? pilotId;
  final int? userId;
  final String name;
  final double lat;
  final double lon;
  final double? alt;
  final double? speed;
  final String? aircraftIcon;
  final String profileType;
  final int? batteryLevel;
  DateTime lastSeen;

  _LivePilot({
    required this.subjectKey,
    this.pilotId,
    this.userId,
    required this.name,
    required this.lat,
    required this.lon,
    this.alt,
    this.speed,
    this.aircraftIcon,
    this.profileType = 'pilot',
    this.batteryLevel,
    DateTime? lastSeen,
  }) : lastSeen = lastSeen ?? DateTime.now();
}

/// Real-time map showing all active pilots.
/// Falls back to the user's GPS position when no other pilots are flying.
class LiveViewScreen extends StatefulWidget {
  const LiveViewScreen({super.key});

  @override
  State<LiveViewScreen> createState() => _LiveViewScreenState();
}

class _LiveViewScreenState extends State<LiveViewScreen> {
  final Map<String, _LivePilot> _pilots = {};
  final MapController _mapController = MapController();
  StreamSubscription<String>? _sseSubscription;
  Timer? _pollTimer;
  TrackingService? _trackingService;
  String? _taskName;
  bool _sseConnected = false;
  bool _hasActiveTask = false;
  bool _initialCenterDone = false;
  bool _userPanned = false;
  bool _followUser = false;
  LiveMapStyle _mapStyle = LiveMapStyle.map;
  LatLng? _userPosition;

  @override
  void initState() {
    super.initState();
    _getUserPosition();
    _connectAndPoll();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final tracking = context.read<TrackingService>();
    if (_trackingService == tracking) return;
    _trackingService?.removeListener(_handleTrackingUpdate);
    _trackingService = tracking;
    _trackingService?.addListener(_handleTrackingUpdate);
  }

  @override
  void dispose() {
    _sseSubscription?.cancel();
    _pollTimer?.cancel();
    _trackingService?.removeListener(_handleTrackingUpdate);
    super.dispose();
  }

  int? get _currentPilotId => context.read<AuthService>().user?.pilotId;
  int? get _currentUserId => context.read<AuthService>().user?.id;

  bool _isCurrentUserPilot(int pilotId) => _currentPilotId == pilotId;

  bool _isCurrentSubject(String subjectKey, int? pilotId, int? userId) {
    if (userId != null && userId == _currentUserId) return true;
    if (pilotId != null && _isCurrentUserPilot(pilotId)) return true;
    return subjectKey == 'user:$_currentUserId';
  }

  String _subjectKeyFor(Map<String, dynamic> json) {
    final subjectKey = json['subject_key'] as String?;
    if (subjectKey != null && subjectKey.isNotEmpty) return subjectKey;
    final pilotId = json['pilot_id'] as int?;
    if (pilotId != null) return 'pilot:$pilotId';
    final userId = json['user_id'] as int?;
    if (userId != null) return 'user:$userId';
    final deviceId = json['device_id'] as String?;
    if (deviceId != null && deviceId.isNotEmpty) return 'device:$deviceId';
    return 'position:${json['id'] ?? DateTime.now().microsecondsSinceEpoch}';
  }

  bool _isManualMapMove(MapEvent event) {
    return event.source == MapEventSource.onDrag ||
        event.source == MapEventSource.onMultiFinger ||
        event.source == MapEventSource.flingAnimationController;
  }

  double _followZoom() {
    final currentZoom = _mapController.camera.zoom;
    return currentZoom < 13 ? 13 : currentZoom;
  }

  void _moveToFollowTarget(LatLng target) {
    _mapController.move(target, _followZoom());
  }

  void _handleTrackingUpdate() {
    if (!_followUser || !mounted) return;
    final trackPos = _trackingService?.lastPosition;
    if (trackPos == null) return;
    _moveToFollowTarget(LatLng(trackPos.lat, trackPos.lon));
  }

  /// Get the user's current GPS position for map centering.
  /// First tries last-known for speed, then falls back to a live fix request.
  Future<void> _getUserPosition() async {
    try {
      // Fast path: last known position (may be stale but gives us something quickly)
      Position? pos = await Geolocator.getLastKnownPosition();

      if (pos == null) {
        // Slow path: request a fresh fix (needed on first boot or after long idle)
        final permission = await Geolocator.checkPermission();
        if (permission == LocationPermission.denied ||
            permission == LocationPermission.deniedForever) {
          return;
        }
        pos = await Geolocator.getCurrentPosition(
          locationSettings: const LocationSettings(
            accuracy: LocationAccuracy.high,
            timeLimit: Duration(seconds: 10),
          ),
        );
      }

      if (mounted) {
        setState(() => _userPosition = LatLng(pos!.latitude, pos.longitude));
        if (_followUser && _trackingService?.lastPosition == null) {
          _moveToFollowTarget(_userPosition!);
        } else if (!_initialCenterDone && !_userPanned) {
          _initialCenterDone = true;
          _mapController.move(_userPosition!, 13);
        }
      }
    } catch (_) {
      // GPS unavailable or timed out — use default center
    }
  }

  /// Try to connect to a task SSE stream, and always start polling for active pilots.
  Future<void> _connectAndPoll() async {
    final api = context.read<ApiService>();

    // 1. Check for active task → SSE stream for real-time updates
    try {
      final taskJson = await api.get(ApiConfig.activeTaskPath);
      if (taskJson.containsKey('task_id')) {
        final taskId = taskJson['task_id'];
        if (mounted) {
          setState(() {
            _taskName = taskJson['task_name'] as String? ?? 'Task';
            _hasActiveTask = true;
          });
        }
        _connectSse(api, taskId);
      }
    } catch (_) {
      // No active task or network error — that's fine
    }

    // 2. Poll for all active pilots every 10 seconds (works with or without a task)
    await _pollActivePilots();
    _pollTimer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _pollActivePilots(),
    );
  }

  /// Fetch all active pilots from the backend.
  Future<void> _pollActivePilots() async {
    if (!mounted) return;
    final api = context.read<ApiService>();
    try {
      final list = await api.getList(ApiConfig.activePilotsPath);
      if (!mounted) return;
      final nextPilots = <String, _LivePilot>{};
      setState(() {
        for (final item in list) {
          final json = item as Map<String, dynamic>;
          final pilot = _parseSsePilot(json);
          if (pilot == null) continue;
          nextPilots[pilot.subjectKey] = pilot;
        }
        _pilots
          ..clear()
          ..addAll(nextPilots);
      });

      // Center map on first data if we haven't centered yet and user hasn't panned
      if (!_initialCenterDone && !_userPanned && _pilots.isNotEmpty) {
        _initialCenterDone = true;
        final first = _pilots.values.first;
        _mapController.move(LatLng(first.lat, first.lon), 13);
      }
    } catch (_) {
      // Network error — keep showing what we have
    }
  }

  /// Connect to the task-specific SSE stream for real-time position updates.
  void _connectSse(ApiService api, int taskId) {
    String? currentEvent;
    String dataBuffer = '';

    _sseSubscription = api.sseStream('/api/track/live/$taskId').listen(
      (line) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
          dataBuffer = '';
        } else if (line.startsWith('data: ')) {
          dataBuffer += line.substring(6);
        } else if (line.startsWith(':')) {
          return; // keepalive
        } else if (line.isEmpty && dataBuffer.isNotEmpty) {
          _processEvent(currentEvent, dataBuffer);
          currentEvent = null;
          dataBuffer = '';
        }

        if (currentEvent != null && dataBuffer.isNotEmpty) {
          _processEvent(currentEvent, dataBuffer);
          currentEvent = null;
          dataBuffer = '';
        }
      },
      onError: (_) {
        if (mounted) setState(() => _sseConnected = false);
        // SSE will reconnect on next poll cycle — polling keeps working
      },
      onDone: () {
        if (mounted) setState(() => _sseConnected = false);
      },
    );

    if (mounted) setState(() => _sseConnected = true);
  }

  void _processEvent(String? event, String data) {
    if (!mounted) return;
    try {
      if (event == 'snapshot') {
        final list = jsonDecode(data) as List<dynamic>;
        setState(() {
          for (final item in list) {
            final json = item as Map<String, dynamic>;
            final pilot = _parseSsePilot(json);
            if (pilot == null) continue;
            _pilots[pilot.subjectKey] = pilot;
          }
        });
      } else if (event == 'position') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilot = _parseSsePilot(json);
        if (pilot == null) return;
        setState(() => _pilots[pilot.subjectKey] = pilot);
      }
    } catch (_) {
      // Malformed SSE data — skip
    }
  }

  _LivePilot? _parseSsePilot(Map<String, dynamic> json) {
    final subjectKey = _subjectKeyFor(json);
    final pilotId = json['pilot_id'] as int?;
    final userId = json['user_id'] as int?;
    if (_isCurrentSubject(subjectKey, pilotId, userId)) {
      _pilots.remove(subjectKey);
      return null;
    }
    // Preserve name from polling data if SSE doesn't include it
    final existing = _pilots[subjectKey];
    final profileType = json['profile_type'] as String? ?? 'pilot';
    return _LivePilot(
      subjectKey: subjectKey,
      pilotId: pilotId,
      userId: userId,
      name: json['pilot_name'] as String? ??
          existing?.name ??
          (profileType == 'driver'
              ? (userId != null ? 'Driver $userId' : 'Driver')
              : pilotId != null
                  ? 'Pilot $pilotId'
                  : 'Tracker'),
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      alt: (json['alt'] as num?)?.toDouble(),
      speed: (json['speed'] as num?)?.toDouble(),
      aircraftIcon: json['aircraft_icon'] as String?,
      profileType: profileType,
      batteryLevel: json['battery_level'] as int?,
    );
  }

  @override
  Widget build(BuildContext context) {
    final tracking = context.watch<TrackingService>();

    // Use tracking position if available, otherwise our own GPS fix
    final trackPos = tracking.lastPosition;
    final center = trackPos != null
        ? LatLng(trackPos.lat, trackPos.lon)
        : _userPosition ?? const LatLng(32.7, -117.2); // San Diego default
    final pilotCount =
        _pilots.length + (tracking.isInFlight && trackPos != null ? 1 : 0);
    final theme = Theme.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(_taskName ?? 'Live View'),
        actions: [
          if (_hasActiveTask)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Icon(
                Icons.circle,
                size: 12,
                color: _sseConnected ? Colors.green : Colors.red,
              ),
            ),
        ],
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: center,
              initialZoom: 13,
              onMapEvent: (event) {
                if (_isManualMapMove(event) && (!_userPanned || _followUser)) {
                  setState(() {
                    _userPanned = true;
                    _followUser = false;
                  });
                }
              },
            ),
            children: [
              TileLayer(
                urlTemplate: _mapStyle.urlTemplate,
                maxZoom: _mapStyle.maxZoom,
                userAgentPackageName: 'com.aervyx.aervyx_mobile',
              ),
              MarkerLayer(
                markers: [
                  // Other pilots
                  ..._pilots.values.map((pilot) => Marker(
                        point: LatLng(pilot.lat, pilot.lon),
                        width: 60,
                        height: 50,
                        child: _PilotMarker(pilot: pilot),
                      )),
                  // User's own position (blue dot)
                  if (trackPos != null)
                    Marker(
                      point: LatLng(trackPos.lat, trackPos.lon),
                      width: 24,
                      height: 24,
                      child: context.read<AuthService>().user?.profileType ==
                              'driver'
                          ? const _OwnDriverMarker()
                          : Container(
                              decoration: BoxDecoration(
                                color: Colors.blue,
                                shape: BoxShape.circle,
                                border:
                                    Border.all(color: Colors.white, width: 3),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withAlpha(60),
                                    blurRadius: 4,
                                  ),
                                ],
                              ),
                            ),
                    ),
                ],
              ),
              AppMapScaleBar(
                padding: EdgeInsets.only(
                  left: 12,
                  bottom: 12 + MediaQuery.of(context).padding.bottom,
                ),
              ),
            ],
          ),

          // Info chips
          Positioned(
            top: 12,
            left: 12,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _InfoChip(
                  icon: Icons.people,
                  text: '$pilotCount tracker${pilotCount == 1 ? '' : 's'} live',
                ),
              ],
            ),
          ),

          Positioned(
            top: 12,
            right: 12,
            child: LiveMapStyleDropdown(
              value: _mapStyle,
              onChanged: (style) => setState(() => _mapStyle = style),
            ),
          ),

          // Re-center button — bottom offset accounts for system nav bar inset
          Positioned(
            bottom: 16 + MediaQuery.of(context).padding.bottom,
            right: 16,
            child: FloatingActionButton.small(
              onPressed: () {
                final LatLng? target;
                if (trackPos != null) {
                  target = LatLng(trackPos.lat, trackPos.lon);
                } else if (_userPosition != null) {
                  target = _userPosition;
                } else {
                  target = null;
                }

                if (target != null) {
                  // Re-enable follow and jump to the current local GPS fix.
                  setState(() {
                    _userPanned = false;
                    _followUser = true;
                  });
                  _moveToFollowTarget(target);
                } else {
                  setState(() {
                    _userPanned = false;
                    _followUser = true;
                  });
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('No GPS fix yet — waiting for location'),
                      duration: Duration(seconds: 2),
                    ),
                  );
                  // Kick off a fresh position request so next tap will work
                  _getUserPosition();
                }
              },
              tooltip: _followUser ? 'Following GPS' : 'Center on GPS',
              backgroundColor: _followUser ? theme.colorScheme.primary : null,
              foregroundColor: _followUser ? theme.colorScheme.onPrimary : null,
              child: const Icon(Icons.my_location),
            ),
          ),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  final IconData icon;
  final String text;

  const _InfoChip({required this.icon, required this.text});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 6),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface.withAlpha(230),
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(30), blurRadius: 4),
        ],
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: theme.colorScheme.primary),
          const SizedBox(width: 5),
          Text(text, style: theme.textTheme.labelSmall),
        ],
      ),
    );
  }
}

class _OwnDriverMarker extends StatelessWidget {
  const _OwnDriverMarker();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.green, width: 2),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(60), blurRadius: 4),
        ],
      ),
      child: const Icon(Icons.directions_car, size: 16, color: Colors.green),
    );
  }
}

class _PilotMarker extends StatelessWidget {
  final _LivePilot pilot;

  const _PilotMarker({required this.pilot});

  IconData _iconForAircraft(String? type) {
    if (pilot.profileType == 'driver') {
      return Icons.directions_car;
    }
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
            color: pilot.profileType == 'driver' ? Colors.green : Colors.blue,
          ),
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
          decoration: BoxDecoration(
            color: Colors.white.withAlpha(210),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            pilot.name.split(' ').first,
            style: const TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.bold,
              color: Colors.black87,
            ),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
