import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../config/api_config.dart';
import 'api_service.dart';

/// A pilot position as seen by a driver.
class DriverPilot {
  final int pilotId;
  final String name;
  final double lat;
  final double lon;
  final double? alt;
  final double? speed;
  final String? aircraftIcon;
  final int? compNumber;
  final bool assigned; // true if this pilot is assigned to this driver
  DateTime lastSeen;

  DriverPilot({
    required this.pilotId,
    required this.name,
    required this.lat,
    required this.lon,
    this.alt,
    this.speed,
    this.aircraftIcon,
    this.compNumber,
    this.assigned = false,
    DateTime? lastSeen,
  }) : lastSeen = lastSeen ?? DateTime.now();
}

/// Service for drivers to view and navigate to assigned pilots.
class DriverService extends ChangeNotifier {
  final ApiService _api;

  final Map<int, DriverPilot> _pilots = {};
  StreamSubscription<String>? _sseSubscription;
  String? _taskName;
  int? _taskId;
  String? _error;
  bool _connected = false;
  bool _showAllPilots = false;

  Map<int, DriverPilot> get pilots => Map.unmodifiable(_pilots);
  String? get taskName => _taskName;
  String? get error => _error;
  bool get connected => _connected;
  bool get showAllPilots => _showAllPilots;

  /// Assigned pilots only.
  List<DriverPilot> get assignedPilots =>
      _pilots.values.where((p) => p.assigned).toList();

  /// Visible pilots based on filter.
  List<DriverPilot> get visiblePilots => _showAllPilots
      ? _pilots.values.toList()
      : assignedPilots;

  DriverService(this._api);

  void toggleShowAllPilots() {
    _showAllPilots = !_showAllPilots;
    notifyListeners();
  }

  /// Connect to the live SSE stream and fetch assigned pilots.
  Future<void> connect() async {
    try {
      // Get active task
      final taskJson = await _api.get(ApiConfig.activeTaskPath);
      if (!taskJson.containsKey('task_id')) {
        _error = 'No active task found';
        notifyListeners();
        return;
      }

      _taskId = taskJson['task_id'] as int;
      _taskName = taskJson['task_name'] as String? ?? 'Task';
      notifyListeners();

      // Fetch assigned pilots
      try {
        final assignedJson =
            await _api.get('/api/driver/assigned-pilots/$_taskId');
        final assigned = (assignedJson['pilots'] as List<dynamic>?)
                ?.map((e) => (e as num).toInt())
                .toSet() ??
            <int>{};

        // Mark assigned pilots
        for (final pilot in _pilots.values) {
          // Will update on next SSE event
          if (assigned.contains(pilot.pilotId)) {
            pilot.assigned;
          }
        }
        // Store assigned IDs for applying to new pilots
        _assignedIds = assigned;
      } catch (_) {
        // Assigned pilots endpoint unavailable — show all
        _showAllPilots = true;
      }

      // Connect to live stream
      _connectToSse();
    } catch (e) {
      _error = 'Failed to connect: $e';
      _connected = false;
      notifyListeners();
    }
  }

  Set<int> _assignedIds = {};

  void _connectToSse() {
    _sseSubscription?.cancel();

    String? currentEvent;
    String dataBuffer = '';

    _sseSubscription = _api.sseStream('/api/track/live/$_taskId').listen(
      (line) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
          dataBuffer = '';
        } else if (line.startsWith('data: ')) {
          dataBuffer += line.substring(6);
        } else if (line.startsWith(':')) {
          return; // Keepalive
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
      onError: (e) {
        _error = 'Connection lost';
        _connected = false;
        notifyListeners();
        // Reconnect after 5 seconds
        Future.delayed(const Duration(seconds: 5), () {
          _connectToSse();
        });
      },
      onDone: () {
        _connected = false;
        notifyListeners();
      },
    );

    _connected = true;
    _error = null;
    notifyListeners();
  }

  void _processEvent(String? event, String data) {
    try {
      if (event == 'snapshot') {
        final list = jsonDecode(data) as List<dynamic>;
        _pilots.clear();
        for (final item in list) {
          final pilot = _parsePilot(item as Map<String, dynamic>);
          _pilots[pilot.pilotId] = pilot;
        }
        notifyListeners();
      } else if (event == 'position') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilot = _parsePilot(json);
        _pilots[pilot.pilotId] = pilot;
        notifyListeners();
      }
    } catch (_) {
      // Malformed SSE data — skip
    }
  }

  DriverPilot _parsePilot(Map<String, dynamic> json) {
    final pilotId = json['pilot_id'] as int;
    return DriverPilot(
      pilotId: pilotId,
      name: json['pilot_name'] as String? ?? 'Pilot #$pilotId',
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      alt: (json['alt'] as num?)?.toDouble(),
      speed: (json['speed'] as num?)?.toDouble(),
      aircraftIcon: json['aircraft_icon'] as String?,
      compNumber: json['comp_number'] as int?,
      assigned: _assignedIds.contains(pilotId),
    );
  }

  void disconnect() {
    _sseSubscription?.cancel();
    _sseSubscription = null;
    _connected = false;
    _pilots.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
