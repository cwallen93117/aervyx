import 'dart:async';

import 'package:battery_plus/battery_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../config/api_config.dart';
import '../models/position.dart' as model;
import '../models/turnpoint.dart';
import 'api_service.dart';
import 'igc_service.dart';

/// GPS tracking zones — determines polling rate near course points.
enum TrackingZone {
  /// On the ground / stationary — 5-second interval
  stationary,

  /// Normal flight, no active task or far from turnpoints — 1 Hz (1 sec)
  normalFlight,

  /// Within 500m of a course point — 5 Hz (200ms)
  approaching,

  /// Within 100m of a course point — 10 Hz (100ms)
  critical,
}

/// GPS tracking service with adaptive rate near competition turnpoints.
///
/// - If the pilot is in an active competition task, the service fetches
///   turnpoint locations and ramps GPS rate when near course points.
/// - If not in a task, it uses the standard 1-second / 5m-distance filter.
class TrackingService extends ChangeNotifier {
  final ApiService _api;
  final IgcService _igc;
  final Battery _battery = Battery();

  // ── Tracking state ──
  bool _isTracking = false;
  model.Position? _lastPosition;
  StreamSubscription<Position>? _locationSubscription;
  Timer? _batteryCheckTimer;
  Timer? _flightTimer;
  Timer? _adaptiveTimer; // drives high-frequency polling in competition mode
  int _positionCount = 0;
  String? _error;
  bool _backendConnected = false;

  // ── Battery protection ──
  int? _batteryThreshold;
  int? _currentBatteryLevel;
  bool _stoppedByBattery = false;

  // ── Flight time ──
  DateTime? _trackingStartTime;
  Duration _flightDuration = Duration.zero;

  // ── Competition / adaptive tracking ──
  ActiveTask? _activeTask;
  TrackingZone _currentZone = TrackingZone.stationary;
  double? _nearestTurnpointDistance;

  /// Speed threshold (m/s) below which we consider the pilot stationary.
  /// ~2 km/h — walking pace or thermal drift.
  static const double _stationarySpeedThreshold = 0.6;

  /// Zone boundary distances in metres.
  static const double _criticalDistance = 100.0;
  static const double _approachingDistance = 500.0;

  // ── Getters ──
  bool get isTracking => _isTracking;
  model.Position? get lastPosition => _lastPosition;
  int get positionCount => _positionCount;
  String? get error => _error;
  bool get backendConnected => _backendConnected;
  int? get batteryThreshold => _batteryThreshold;
  int? get currentBatteryLevel => _currentBatteryLevel;
  bool get stoppedByBattery => _stoppedByBattery;
  Duration get flightDuration => _flightDuration;
  ActiveTask? get activeTask => _activeTask;
  TrackingZone get currentZone => _currentZone;
  double? get nearestTurnpointDistance => _nearestTurnpointDistance;
  bool get inCompetitionMode => _activeTask != null;

  /// Path to the last saved IGC file (shown briefly after stop).
  String? _lastSavedIgcPath;
  String? get lastSavedIgcPath => _lastSavedIgcPath;

  TrackingService(this._api, this._igc);

  /// Set the battery threshold percentage. null to disable.
  void setBatteryThreshold(int? threshold) {
    _batteryThreshold = threshold;
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Start / Stop
  // ═══════════════════════════════════════════════════════════════════════════

  /// Start GPS tracking.
  Future<void> startTracking() async {
    if (_isTracking) return;

    // Check and request permissions
    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
      if (permission == LocationPermission.denied) {
        _error = 'Location permission denied';
        notifyListeners();
        return;
      }
    }
    if (permission == LocationPermission.deniedForever) {
      _error = 'Location permission permanently denied. Enable in settings.';
      notifyListeners();
      return;
    }

    _isTracking = true;
    _positionCount = 0;
    _error = null;
    _stoppedByBattery = false;
    _trackingStartTime = DateTime.now();
    _flightDuration = Duration.zero;
    _currentZone = TrackingZone.stationary;
    _nearestTurnpointDistance = null;
    _startFlightTimer();
    notifyListeners();

    // Try to fetch active task turnpoints from the backend
    await _fetchActiveTask();

    if (_activeTask != null) {
      // Competition mode — use adaptive rate polling
      _startAdaptiveTracking();
    } else {
      // Free-flight mode — standard 1 Hz / 5m distance filter
      _startStandardTracking();
    }

    // Battery monitoring
    _startBatteryMonitor();
  }

  /// Stop GPS tracking and auto-save the flight as an IGC file.
  Future<void> stopTracking() async {
    _locationSubscription?.cancel();
    _locationSubscription = null;
    _adaptiveTimer?.cancel();
    _adaptiveTimer = null;
    _batteryCheckTimer?.cancel();
    _batteryCheckTimer = null;
    _flightTimer?.cancel();
    _flightTimer = null;
    // Keep final flight duration
    if (_trackingStartTime != null) {
      _flightDuration = DateTime.now().difference(_trackingStartTime!);
    }
    _isTracking = false;
    _backendConnected = false;
    _activeTask = null;
    _currentZone = TrackingZone.stationary;
    notifyListeners();

    // Auto-save flight as IGC file
    try {
      final trackPoints = _igc.currentTrackPointCount;
      _lastSavedIgcPath = await _igc.saveCurrentFlight();
      if (_lastSavedIgcPath != null) {
        _error = 'Flight saved ($trackPoints points)';
      } else {
        _error = 'Flight too short to save ($trackPoints points recorded)';
      }
    } catch (e) {
      _lastSavedIgcPath = null;
      _error = 'Failed to save flight: $e';
    }
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Standard (free-flight) tracking — 1 Hz, 5m distance filter
  // ═══════════════════════════════════════════════════════════════════════════

  void _startStandardTracking() {
    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5, // metres
    );

    _currentZone = TrackingZone.normalFlight;
    _locationSubscription =
        Geolocator.getPositionStream(locationSettings: locationSettings)
            .listen(_onLocationUpdate, onError: _onLocationError);
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Adaptive (competition) tracking
  // ═══════════════════════════════════════════════════════════════════════════

  /// Fetch the pilot's active task + turnpoints from the backend.
  Future<void> _fetchActiveTask() async {
    try {
      final json = await _api.get(ApiConfig.activeTaskPath);
      if (json.containsKey('task_id')) {
        _activeTask = ActiveTask.fromJson(json);
      } else {
        _activeTask = null;
      }
    } catch (_) {
      // No active task or backend unreachable — use standard tracking
      _activeTask = null;
    }
  }

  /// Start adaptive tracking that adjusts GPS rate based on proximity
  /// to competition turnpoints.
  void _startAdaptiveTracking() {
    // Start with a high-accuracy stream at 0 distance filter (get every fix)
    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.best,
      distanceFilter: 0,
    );

    _locationSubscription =
        Geolocator.getPositionStream(locationSettings: locationSettings)
            .listen(_onAdaptiveLocationUpdate, onError: _onLocationError);
  }

  /// Track last time we sent a position — used to throttle sends per zone.
  DateTime _lastSendTime = DateTime.fromMillisecondsSinceEpoch(0);

  /// Handle each GPS fix in competition mode. Determines the zone and
  /// throttles sends accordingly.
  Future<void> _onAdaptiveLocationUpdate(Position geoPos) async {
    if (!_isTracking || _activeTask == null) return;

    // Determine zone based on nearest turnpoint distance
    final nearest = _findNearestTurnpointDistance(geoPos.latitude, geoPos.longitude);
    _nearestTurnpointDistance = nearest;

    // Determine if pilot is stationary
    final isStationary = geoPos.speed < _stationarySpeedThreshold;

    TrackingZone newZone;
    Duration minInterval;

    if (isStationary) {
      newZone = TrackingZone.stationary;
      minInterval = const Duration(seconds: 5);
    } else if (nearest != null && nearest <= _criticalDistance) {
      newZone = TrackingZone.critical;
      minInterval = const Duration(milliseconds: 100);
    } else if (nearest != null && nearest <= _approachingDistance) {
      newZone = TrackingZone.approaching;
      minInterval = const Duration(milliseconds: 200);
    } else {
      newZone = TrackingZone.normalFlight;
      minInterval = const Duration(seconds: 1);
    }

    // Update zone if changed
    if (newZone != _currentZone) {
      _currentZone = newZone;
      notifyListeners();
    }

    // Throttle: only send if enough time has passed for this zone
    final now = DateTime.now();
    if (now.difference(_lastSendTime) >= minInterval) {
      _lastSendTime = now;
      await _sendPosition(geoPos);
    }
  }

  /// Find the distance to the nearest turnpoint, or null if no turnpoints.
  double? _findNearestTurnpointDistance(double lat, double lon) {
    if (_activeTask == null || _activeTask!.turnpoints.isEmpty) return null;

    double? minDist;
    for (final tp in _activeTask!.turnpoints) {
      final d = tp.distanceTo(lat, lon);
      if (minDist == null || d < minDist) {
        minDist = d;
      }
    }
    return minDist;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Position sending (shared by both modes)
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _sendPosition(Position geoPos) async {
    // Record trackpoint for IGC file
    _igc.addTrackPoint(geoPos);

    // Always update local position for UI display — regardless of backend
    _lastPosition = model.Position(
      lat: geoPos.latitude,
      lon: geoPos.longitude,
      alt: geoPos.altitude,
      speed: geoPos.speed,
      heading: geoPos.heading,
      accuracy: geoPos.accuracy,
      timestamp: geoPos.timestamp.toUtc(),
    );
    _positionCount++;

    // Try to send to backend (non-blocking for UI)
    final payload = {
      'lat': geoPos.latitude,
      'lon': geoPos.longitude,
      'alt': geoPos.altitude,
      'speed': geoPos.speed,
      'heading': geoPos.heading,
      'accuracy': geoPos.accuracy,
      'timestamp': geoPos.timestamp.toUtc().toIso8601String(),
      'source': 'app',
      if (_activeTask != null) 'task_id': _activeTask!.taskId,
      'zone': _currentZone.name,
    };

    try {
      await _api.post(ApiConfig.trackPositionPath, body: payload);
      _error = null;
      _backendConnected = true;
    } catch (e) {
      // Backend unreachable — GPS still works, data still recorded locally
      _backendConnected = false;
      // Only show error if we haven't shown it recently (avoid spam)
      _error = 'Backend offline — recording locally';
    }
    notifyListeners();
  }

  /// Standard mode callback — sends every position it receives.
  Future<void> _onLocationUpdate(Position geoPos) async {
    if (!_isTracking) return;
    await _sendPosition(geoPos);
  }

  void _onLocationError(dynamic error) {
    _error = 'Location error: $error';
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Flight timer & battery
  // ═══════════════════════════════════════════════════════════════════════════

  void _startFlightTimer() {
    _flightTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_trackingStartTime != null) {
        _flightDuration = DateTime.now().difference(_trackingStartTime!);
        notifyListeners();
      }
    });
  }

  void _startBatteryMonitor() {
    _checkBattery();
    _batteryCheckTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _checkBattery(),
    );
  }

  Future<void> _checkBattery() async {
    try {
      _currentBatteryLevel = await _battery.batteryLevel;
      if (_batteryThreshold != null &&
          _currentBatteryLevel != null &&
          _currentBatteryLevel! <= _batteryThreshold! &&
          _isTracking) {
        _stoppedByBattery = true;
        _error =
            'Tracking stopped — battery at $_currentBatteryLevel% (threshold: $_batteryThreshold%)';
        stopTracking();
      }
      notifyListeners();
    } catch (_) {
      // Battery level unavailable
    }
  }

  @override
  void dispose() {
    stopTracking();
    _batteryCheckTimer?.cancel();
    _flightTimer?.cancel();
    _adaptiveTimer?.cancel();
    super.dispose();
  }
}
