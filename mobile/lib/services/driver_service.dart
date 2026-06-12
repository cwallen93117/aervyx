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
  DateTime? lastSeen;

  // Landing/pickup status
  String status; // flying | landed | ready | picked_up
  DateTime? landedAt;
  DateTime? readyAt;
  int? landingId;

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
    this.status = 'flying',
    this.landedAt,
    this.readyAt,
    this.landingId,
    this.lastSeen,
  });

  /// Minutes until pilot is ready for pickup.
  int get minutesUntilReady {
    if (readyAt == null) return 0;
    final diff = readyAt!.difference(DateTime.now().toUtc()).inMinutes;
    return diff > 0 ? diff : 0;
  }

  bool get isReady =>
      readyAt != null && DateTime.now().toUtc().isAfter(readyAt!);

  /// True if this pilot has landed and needs pickup.
  bool get needsPickup => status == 'landed' || status == 'ready';
}

class DriverSosAlert {
  final String id;
  final int? pilotId;
  final String? pilotName;
  final double lat;
  final double lon;
  final double? alt;
  final String? message;
  final DateTime timestamp;
  final String status;

  const DriverSosAlert({
    required this.id,
    required this.pilotId,
    required this.pilotName,
    required this.lat,
    required this.lon,
    required this.alt,
    required this.message,
    required this.timestamp,
    required this.status,
  });

  factory DriverSosAlert.fromJson(Map<String, dynamic> json) {
    return DriverSosAlert(
      id: json['id'] as String,
      pilotId: json['pilot_id'] as int?,
      pilotName: json['pilot_name'] as String?,
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      alt: (json['alt'] as num?)?.toDouble(),
      message: json['message'] as String?,
      timestamp:
          DateTime.tryParse(json['timestamp'] as String? ?? '')?.toUtc() ??
              DateTime.now().toUtc(),
      status: json['status'] as String? ?? 'active',
    );
  }

  String get displayPilotName => pilotName ?? 'Pilot ${pilotId ?? ''}'.trim();
}

abstract class DriverSosNotifier {
  Future<void> showSosAlert(DriverSosAlert alert);
}

/// Service for drivers to view and navigate to assigned pilots.
class DriverService extends ChangeNotifier {
  final ApiService _api;
  final DriverSosNotifier? _sosNotifier;

  final Map<int, DriverPilot> _pilots = {};
  final Set<String> _notifiedSosAlertIds = {};
  List<DriverSosAlert> _activeSosAlerts = [];
  StreamSubscription<String>? _sseSubscription;
  Timer? _pollTimer;
  Timer? _reconnectTimer;
  String? _taskName;
  int? _taskId;
  String? _error;
  bool _connected = false;
  bool _showAllPilots = true;
  bool _closed = false;

  Map<int, DriverPilot> get pilots => Map.unmodifiable(_pilots);
  String? get taskName => _taskName;
  int? get taskId => _taskId;
  bool get hasActiveTask => _taskId != null;
  String? get error => _error;
  bool get connected => _connected;
  bool get showAllPilots => _showAllPilots;

  /// Assigned pilots only.
  List<DriverPilot> get assignedPilots =>
      _pilots.values.where((p) => p.assigned).toList();

  /// Visible pilots based on filter.
  List<DriverPilot> get visiblePilots => _showAllPilots
      ? (_pilots.values.toList()
        ..sort((a, b) => a.name.toLowerCase().compareTo(b.name.toLowerCase())))
      : assignedPilots;

  List<DriverSosAlert> get activeSosAlerts =>
      List.unmodifiable(_activeSosAlerts);

  DriverService(this._api, {DriverSosNotifier? sosNotifier})
      : _sosNotifier = sosNotifier;

  void toggleShowAllPilots() {
    _showAllPilots = !_showAllPilots;
    notifyListeners();
  }

  /// Connect to the live SSE stream and fetch assigned pilots.
  Future<void> connect() async {
    _closed = false;
    _reconnectTimer?.cancel();
    _pollTimer?.cancel();
    try {
      // Get active task
      final taskJson = await _api.get(ApiConfig.activeTaskPath);
      if (!taskJson.containsKey('task_id')) {
        await _sseSubscription?.cancel();
        _sseSubscription = null;
        _taskId = null;
        _taskName = null;
        _assignedIds = {};
        _error = null;
        _connected = false;
        notifyListeners();
        await _pollDriverSnapshot();
        _startPolling();
        return;
      }

      _taskId = taskJson['task_id'] as int;
      _taskName = taskJson['task_name'] as String? ?? 'Task';
      notifyListeners();

      // Fetch assigned pilots
      try {
        final assignedJson =
            await _api.getList(ApiConfig.driverAssignedPilotsPath(_taskId!));
        final assigned = assignedJson
            .map((item) => (item as Map<String, dynamic>)['pilot_id'] as int?)
            .whereType<int>()
            .toSet();

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
      await _pollDriverSnapshot();
      _startPolling();
    } catch (e) {
      _error = 'Failed to connect: $e';
      _connected = false;
      notifyListeners();
      await _pollDriverSnapshot();
      _startPolling();
    }
  }

  Set<int> _assignedIds = {};

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(
      const Duration(seconds: 10),
      (_) => _pollDriverSnapshot(),
    );
  }

  Future<void> _pollDriverSnapshot() async {
    await _pollActivePilots();
    await _pollSosAlerts();
  }

  Future<void> _pollActivePilots() async {
    if (_closed) return;
    try {
      final list = await _api.getList(ApiConfig.activePilotsPath);
      if (_closed) return;
      final nextPilots = <int, DriverPilot>{};
      for (final item in list) {
        final pilot = _parsePilot(item as Map<String, dynamic>);
        if (pilot == null) continue;
        final existing = _pilots[pilot.pilotId];
        _preservePickupState(pilot, existing);
        nextPilots[pilot.pilotId] = pilot;
      }
      _pilots
        ..clear()
        ..addAll(nextPilots);
      _error = null;
      notifyListeners();
    } catch (_) {
      // Keep existing last-known pilot positions if polling is temporarily down.
    }
  }

  Future<void> _pollSosAlerts() async {
    if (_closed) return;
    try {
      final list = await _api.getList(ApiConfig.driverSosAlertsPath);
      if (_closed) return;
      final alerts = list
          .map((item) => DriverSosAlert.fromJson(item as Map<String, dynamic>))
          .toList();
      _activeSosAlerts = alerts;
      for (final alert in alerts) {
        if (_notifiedSosAlertIds.add(alert.id)) {
          await _sosNotifier?.showSosAlert(alert);
        }
      }
      notifyListeners();
    } catch (_) {
      // Keep existing active alerts when polling temporarily fails.
    }
  }

  void _connectToSse() {
    if (_closed || _taskId == null) return;
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
        _reconnectTimer?.cancel();
        _reconnectTimer = Timer(const Duration(seconds: 5), () {
          if (!_closed && _taskId != null) _connectToSse();
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

  /// Number of pilots awaiting pickup (landed or ready).
  int get pilotsAwaitingPickup =>
      _pilots.values.where((p) => p.needsPickup).length;

  void _processEvent(String? event, String data) {
    try {
      if (event == 'snapshot') {
        final list = jsonDecode(data) as List<dynamic>;
        for (final item in list) {
          final pilot = _parsePilot(item as Map<String, dynamic>);
          if (pilot == null) continue;
          _preservePickupState(pilot, _pilots[pilot.pilotId]);
          _pilots[pilot.pilotId] = pilot;
        }
        notifyListeners();
      } else if (event == 'position') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilot = _parsePilot(json);
        if (pilot == null) return;
        _preservePickupState(pilot, _pilots[pilot.pilotId]);
        _pilots[pilot.pilotId] = pilot;
        notifyListeners();
      } else if (event == 'landing') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilotId = json['pilot_id'] as int;
        final pilot = _pilots[pilotId];
        if (pilot != null) {
          pilot.status = 'landed';
          pilot.landedAt = DateTime.parse(json['landed_at'] as String);
          pilot.readyAt = DateTime.parse(json['ready_at'] as String);
          pilot.landingId = json['landing_id'] as int?;
          notifyListeners();
        }
      } else if (event == 'landing_cancelled') {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final pilotId = json['pilot_id'] as int;
        final pilot = _pilots[pilotId];
        if (pilot != null) {
          pilot.status = 'flying';
          pilot.landedAt = null;
          pilot.readyAt = null;
          pilot.landingId = null;
          notifyListeners();
        }
      }
    } catch (_) {
      // Malformed SSE data — skip
    }
  }

  void _preservePickupState(DriverPilot pilot, DriverPilot? existing) {
    if (existing != null && existing.needsPickup) {
      pilot.status = existing.status;
      pilot.landedAt = existing.landedAt;
      pilot.readyAt = existing.readyAt;
      pilot.landingId = existing.landingId;
    }
  }

  DriverPilot? _parsePilot(Map<String, dynamic> json) {
    if (json['profile_type'] == 'driver' || json['pilot_id'] == null) {
      return null;
    }
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
      lastSeen: DateTime.tryParse(json['timestamp'] as String? ?? ''),
    );
  }

  void disconnect() {
    _closed = true;
    _pollTimer?.cancel();
    _pollTimer = null;
    _reconnectTimer?.cancel();
    _reconnectTimer = null;
    _sseSubscription?.cancel();
    _sseSubscription = null;
    _taskId = null;
    _taskName = null;
    _error = null;
    _assignedIds = {};
    _connected = false;
    _pilots.clear();
    _activeSosAlerts = [];
    _notifiedSosAlertIds.clear();
    notifyListeners();
  }

  @override
  void dispose() {
    disconnect();
    super.dispose();
  }
}
