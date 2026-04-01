import 'dart:async';
import 'dart:math';

import 'package:battery_plus/battery_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../config/api_config.dart';
import '../models/position.dart' as model;
import '../models/turnpoint.dart';
import 'api_service.dart';
import 'background_service.dart';
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

/// Tracking lifecycle state machine.
enum TrackingState {
  /// Not tracking — idle.
  idle,

  /// GPS running, waiting for takeoff detection.
  preFlight,

  /// Actively recording a flight.
  inFlight,

  /// Flight saved, watching for re-launch (low-power GPS).
  monitoring,
}

/// Sport type — determines takeoff detection thresholds.
enum SportType { paraglider, hangGlider, glider }

/// Takeoff detection thresholds per sport.
class _TakeoffThresholds {
  final double altitudeGainMeters;
  final double speedThresholdMs;

  const _TakeoffThresholds({
    required this.altitudeGainMeters,
    required this.speedThresholdMs,
  });
}

/// GPS tracking service with adaptive rate, flight detection, landing
/// detection, and multi-flight monitoring mode.
class TrackingService extends ChangeNotifier {
  final ApiService _api;
  final IgcService _igc;
  final Battery _battery = Battery();

  // ── Core state ──
  TrackingState _trackingState = TrackingState.idle;
  model.Position? _lastPosition;
  StreamSubscription<Position>? _locationSubscription;
  Timer? _batteryCheckTimer;
  Timer? _flightTimer;
  Timer? _adaptiveTimer;
  Timer? _flightResetTimer;
  Timer? _monitoringTimer;
  int _positionCount = 0;
  String? _error;
  bool _backendConnected = false;
  Timer? _heartbeatTimer;

  // ── Offline position buffer ──
  final List<Map<String, dynamic>> _positionBuffer = [];
  static const int _maxBufferSize = 5000;

  // ── Battery protection ──
  int? _batteryThreshold = 15;
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
  static const double _stationarySpeedThreshold = 0.6;

  /// Zone boundary distances in metres.
  static const double _criticalDistance = 100.0;
  static const double _approachingDistance = 500.0;

  // ── Sport & flight detection settings ──
  SportType _sportType = SportType.paraglider;
  bool _multiFlightEnabled = true;

  /// Hardcoded defaults per sport — overridable from admin API.
  static const Map<SportType, _TakeoffThresholds> _defaultTakeoffThresholds = {
    SportType.paraglider: _TakeoffThresholds(
      altitudeGainMeters: 10.0, // 30 ft
      speedThresholdMs: 2.2, // 5 mph
    ),
    SportType.hangGlider: _TakeoffThresholds(
      altitudeGainMeters: 10.0, // 30 ft
      speedThresholdMs: 3.6, // 8 mph
    ),
    SportType.glider: _TakeoffThresholds(
      altitudeGainMeters: 15.0, // 50 ft
      speedThresholdMs: 6.7, // 15 mph
    ),
  };

  /// Current effective thresholds (may be overridden by admin).
  _TakeoffThresholds? _adminTakeoffThresholds;

  _TakeoffThresholds get _takeoffThresholds =>
      _adminTakeoffThresholds ??
      _defaultTakeoffThresholds[_sportType]!;

  // ── Landing detection settings (overridable from admin) ──
  double _landingSpeedMs = 4.47; // 10 mph
  double _landingAltToleranceM = 30.5; // 100 ft
  int _landingConfirmSeconds = 15;
  int _landingCountdownSeconds = 15;

  // ── Pre-flight buffer ──
  final List<Position> _preFlightBuffer = [];
  static const int _preFlightBufferMaxSeconds = 30;
  double? _preFlightBaseAltitude;

  // ── Landing detection state ──
  DateTime? _landingDetectionStart;
  bool _landingCountdownActive = false;
  DateTime? _landingCountdownStart;
  final List<double> _recentAltitudes = []; // last 2 min
  final List<DateTime> _recentAltitudeTimes = [];

  // ── Monitoring state ──
  double? _takeoffLat;
  double? _takeoffLon;
  int _flightNumberToday = 0;

  // ── Getters ──
  bool get isTracking =>
      _trackingState != TrackingState.idle;
  bool get isInFlight =>
      _trackingState == TrackingState.inFlight;
  bool get isPreFlight =>
      _trackingState == TrackingState.preFlight;
  bool get isMonitoring =>
      _trackingState == TrackingState.monitoring;
  TrackingState get trackingState => _trackingState;
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
  SportType get sportType => _sportType;
  bool get multiFlightEnabled => _multiFlightEnabled;
  int get bufferedPositionCount => _positionBuffer.length;
  bool get landingCountdownActive => _landingCountdownActive;
  /// True when landing conditions are detected but not yet confirmed.
  bool get landingDetected =>
      _landingDetectionStart != null &&
      _trackingState == TrackingState.inFlight;
  int get landingCountdownRemaining {
    if (!_landingCountdownActive || _landingCountdownStart == null) return 0;
    final elapsed = DateTime.now().difference(_landingCountdownStart!).inSeconds;
    return max(0, _landingCountdownSeconds - elapsed);
  }

  /// Path to the last saved IGC file (shown briefly after stop).
  String? _lastSavedIgcPath;
  String? get lastSavedIgcPath => _lastSavedIgcPath;

  TrackingService(this._api, this._igc) {
    // Start server heartbeat immediately so the LED shows status on app open
    _startHeartbeat();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Server heartbeat — checks connectivity even when not tracking
  // ═══════════════════════════════════════════════════════════════════════════

  /// Ping the server periodically to keep the connection status LED accurate.
  void _startHeartbeat() {
    // Check immediately on startup
    _checkServerHealth();
    // Then every 30 seconds
    _heartbeatTimer?.cancel();
    _heartbeatTimer = Timer.periodic(
      const Duration(seconds: 30),
      (_) => _checkServerHealth(),
    );
  }

  Future<void> _checkServerHealth() async {
    // Skip if actively tracking — position uploads already report connectivity
    if (_trackingState == TrackingState.inFlight) return;
    try {
      await _api.get(ApiConfig.mePath);
      _backendConnected = true;
    } on ApiException {
      // Server reachable but returned an error (e.g. 401) — still "connected"
      _backendConnected = true;
    } catch (_) {
      // Network error — server unreachable
      _backendConnected = false;
    }
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Settings
  // ═══════════════════════════════════════════════════════════════════════════

  /// Set the battery threshold percentage. null to disable.
  void setBatteryThreshold(int? threshold) {
    _batteryThreshold = threshold;
    notifyListeners();
  }

  /// Set the sport type for takeoff detection.
  void setSportType(SportType sport) {
    _sportType = sport;
    notifyListeners();
  }

  /// Enable/disable multi-flight monitoring mode.
  void setMultiFlightEnabled(bool enabled) {
    _multiFlightEnabled = enabled;
    notifyListeners();
  }

  /// Apply admin-provided flight detection settings from the backend.
  void applyAdminSettings(Map<String, dynamic> config) {
    // Takeoff thresholds — per sport
    final sport = _sportType;
    final altKey = '${sport.name}_takeoff_alt_ft';
    final speedKey = '${sport.name}_takeoff_speed_mph';
    if (config.containsKey(altKey) && config.containsKey(speedKey)) {
      _adminTakeoffThresholds = _TakeoffThresholds(
        altitudeGainMeters: (config[altKey] as num).toDouble() * 0.3048,
        speedThresholdMs: (config[speedKey] as num).toDouble() * 0.44704,
      );
    }
    // Landing thresholds
    if (config.containsKey('landing_speed_mph')) {
      _landingSpeedMs = (config['landing_speed_mph'] as num).toDouble() * 0.44704;
    }
    if (config.containsKey('landing_alt_tolerance_ft')) {
      _landingAltToleranceM =
          (config['landing_alt_tolerance_ft'] as num).toDouble() * 0.3048;
    }
    if (config.containsKey('landing_confirm_seconds')) {
      _landingConfirmSeconds = (config['landing_confirm_seconds'] as num).toInt();
    }
    if (config.containsKey('landing_countdown_seconds')) {
      _landingCountdownSeconds =
          (config['landing_countdown_seconds'] as num).toInt();
    }
  }

  /// Fetch flight detection settings from the backend.
  Future<void> fetchFlightDetectionSettings() async {
    try {
      final config = await _api.get(ApiConfig.flightDetectionConfigPath);
      applyAdminSettings(config);
    } catch (_) {
      // Backend unreachable — use hardcoded defaults
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Start / Stop / Force-Start
  // ═══════════════════════════════════════════════════════════════════════════

  /// Start GPS tracking — enters preFlight and waits for takeoff detection.
  Future<void> startTracking() async {
    if (_trackingState != TrackingState.idle &&
        _trackingState != TrackingState.monitoring) return;

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

    _flightResetTimer?.cancel();
    _flightResetTimer = null;
    _monitoringTimer?.cancel();
    _monitoringTimer = null;

    _trackingState = TrackingState.preFlight;
    _positionCount = 0;
    _error = null;
    _stoppedByBattery = false;
    _flightDuration = Duration.zero;
    _trackingStartTime = null;
    _currentZone = TrackingZone.stationary;
    _nearestTurnpointDistance = null;
    _preFlightBuffer.clear();
    _preFlightBaseAltitude = null;
    _landingDetectionStart = null;
    _landingCountdownActive = false;
    _landingCountdownStart = null;
    _recentAltitudes.clear();
    _recentAltitudeTimes.clear();

    if (_flightNumberToday == 0) {
      _flightNumberToday = 1;
    }

    // Update notification for pre-flight state
    BackgroundTrackingService.updateNotification(
      title: 'Aervyx — Pre-Flight',
      content: 'Waiting for takeoff...',
    );

    notifyListeners();

    // Fetch settings from backend
    await _fetchActiveTask();
    await fetchFlightDetectionSettings();

    // Start GPS stream
    _startGpsStream();

    // Start background foreground service (keeps GPS alive when app is backgrounded)
    try {
      await BackgroundTrackingService.start();
    } catch (_) {
      // Background service unavailable — foreground-only mode
    }

    // Battery monitoring
    _startBatteryMonitor();
  }

  /// Force-start recording immediately — bypass takeoff detection.
  Future<void> forceStartRecording() async {
    if (_trackingState == TrackingState.idle) {
      await startTracking();
    }
    if (_trackingState == TrackingState.preFlight) {
      _transitionToInFlight();
    }
  }

  /// Cancel the landing countdown (pilot cancels auto-stop).
  void cancelLandingCountdown() {
    _landingCountdownActive = false;
    _landingCountdownStart = null;
    _landingDetectionStart = null;
    _error = null;
    notifyListeners();
  }

  /// Stop GPS tracking completely and save any active flight.
  Future<void> stopTracking() async {
    final wasInFlight = _trackingState == TrackingState.inFlight;

    _locationSubscription?.cancel();
    _locationSubscription = null;
    _adaptiveTimer?.cancel();
    _adaptiveTimer = null;
    _batteryCheckTimer?.cancel();
    _batteryCheckTimer = null;
    _flightTimer?.cancel();
    _flightTimer = null;
    _monitoringTimer?.cancel();
    _monitoringTimer = null;
    _landingCountdownActive = false;
    _landingCountdownStart = null;

    // Keep final flight duration
    if (_trackingStartTime != null) {
      _flightDuration = DateTime.now().difference(_trackingStartTime!);
    }

    _trackingState = TrackingState.idle;
    _backendConnected = false;
    _activeTask = null;
    _currentZone = TrackingZone.stationary;
    _flightNumberToday = 0;

    // Stop background foreground service
    try {
      await BackgroundTrackingService.stop();
    } catch (_) {
      // Background service was not running
    }

    notifyListeners();

    // Save flight if we were recording
    if (wasInFlight) {
      await _saveCurrentFlight();
    } else {
      _igc.discardCurrentTrack();
    }

    // Final drain attempt for any buffered positions
    if (_positionBuffer.isNotEmpty) {
      await _drainPositionBuffer(limit: _positionBuffer.length);
    }

    // Reset flight duration display after 3 seconds
    _flightResetTimer?.cancel();
    _flightResetTimer = Timer(const Duration(seconds: 3), () {
      _flightDuration = Duration.zero;
      _trackingStartTime = null;
      notifyListeners();
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // GPS Stream
  // ═══════════════════════════════════════════════════════════════════════════

  void _startGpsStream() {
    _locationSubscription?.cancel();

    if (_activeTask != null) {
      // Competition mode — high-accuracy, 0 distance filter
      const settings = LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 0,
      );
      _locationSubscription =
          Geolocator.getPositionStream(locationSettings: settings)
              .listen(_onPositionUpdate, onError: _onLocationError);
    } else {
      // Free-flight — high accuracy, 5m filter
      const settings = LocationSettings(
        accuracy: LocationAccuracy.high,
        distanceFilter: 5,
      );
      _locationSubscription =
          Geolocator.getPositionStream(locationSettings: settings)
              .listen(_onPositionUpdate, onError: _onLocationError);
    }
  }

  /// Start a low-power GPS stream for monitoring mode.
  void _startMonitoringGps() {
    _locationSubscription?.cancel();
    // Poll every ~15 seconds by using a large distance filter
    const settings = LocationSettings(
      accuracy: LocationAccuracy.low,
      distanceFilter: 30,
    );
    _locationSubscription =
        Geolocator.getPositionStream(locationSettings: settings)
            .listen(_onMonitoringPositionUpdate, onError: _onLocationError);

    // Also set a periodic timer to ensure we get updates even if stationary
    _monitoringTimer?.cancel();
    _monitoringTimer = Timer.periodic(
      const Duration(seconds: 15),
      (_) => _checkMonitoringConditions(),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Position Handling — unified callback
  // ═══════════════════════════════════════════════════════════════════════════

  /// Track last time we sent a position — used to throttle sends per zone.
  DateTime _lastSendTime = DateTime.fromMillisecondsSinceEpoch(0);

  Future<void> _onPositionUpdate(Position geoPos) async {
    // Update UI position regardless of state
    _updateLastPosition(geoPos);

    switch (_trackingState) {
      case TrackingState.idle:
        return;

      case TrackingState.preFlight:
        _handlePreFlight(geoPos);
        return;

      case TrackingState.inFlight:
        await _handleInFlight(geoPos);
        return;

      case TrackingState.monitoring:
        // Shouldn't happen — monitoring uses its own callback
        return;
    }
  }

  void _updateLastPosition(Position geoPos) {
    _lastPosition = model.Position(
      lat: geoPos.latitude,
      lon: geoPos.longitude,
      alt: geoPos.altitude,
      speed: geoPos.speed,
      heading: geoPos.heading,
      accuracy: geoPos.accuracy,
      timestamp: geoPos.timestamp.toUtc(),
    );
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Pre-Flight — takeoff detection
  // ═══════════════════════════════════════════════════════════════════════════

  void _handlePreFlight(Position geoPos) {
    // Add to circular buffer (last 30 seconds)
    _preFlightBuffer.add(geoPos);
    _preFlightBaseAltitude ??= geoPos.altitude;

    // Trim buffer to 30 seconds
    while (_preFlightBuffer.length > 1) {
      final age = geoPos.timestamp.difference(_preFlightBuffer.first.timestamp);
      if (age.inSeconds > _preFlightBufferMaxSeconds) {
        _preFlightBuffer.removeAt(0);
      } else {
        break;
      }
    }

    // Update base altitude to the minimum in the buffer
    double minAlt = geoPos.altitude;
    for (final p in _preFlightBuffer) {
      if (p.altitude < minAlt) minAlt = p.altitude;
    }
    _preFlightBaseAltitude = minAlt;

    // Check takeoff conditions
    final altGain = geoPos.altitude - _preFlightBaseAltitude!;
    final speed = geoPos.speed;
    final thresholds = _takeoffThresholds;

    // Combined trigger: (alt gain >= threshold AND speed > threshold)
    // OR (alt gain >= 2x threshold regardless of speed)
    final normalTakeoff = altGain >= thresholds.altitudeGainMeters &&
        speed > thresholds.speedThresholdMs;
    final strongAltTakeoff = altGain >= thresholds.altitudeGainMeters * 2;

    if (normalTakeoff || strongAltTakeoff) {
      _transitionToInFlight();
    }

    notifyListeners();
  }

  void _transitionToInFlight() {
    _trackingState = TrackingState.inFlight;
    _trackingStartTime = DateTime.now();

    // Record takeoff position for monitoring radius
    if (_preFlightBuffer.isNotEmpty) {
      _takeoffLat = _preFlightBuffer.first.latitude;
      _takeoffLon = _preFlightBuffer.first.longitude;
    } else if (_lastPosition != null) {
      _takeoffLat = _lastPosition!.lat;
      _takeoffLon = _lastPosition!.lon;
    }

    // Flush pre-flight buffer into IGC recording
    for (final pos in _preFlightBuffer) {
      _igc.addTrackPoint(pos);
    }
    _positionCount += _preFlightBuffer.length;
    _preFlightBuffer.clear();

    // Start flight timer
    _startFlightTimer();

    // Reset landing detection
    _landingDetectionStart = null;
    _landingCountdownActive = false;
    _recentAltitudes.clear();
    _recentAltitudeTimes.clear();

    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // In-Flight — recording + landing detection
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _handleInFlight(Position geoPos) async {
    // Competition mode throttling
    if (_activeTask != null) {
      final nearest =
          _findNearestTurnpointDistance(geoPos.latitude, geoPos.longitude);
      _nearestTurnpointDistance = nearest;

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

      if (newZone != _currentZone) {
        _currentZone = newZone;
      }

      final now = DateTime.now();
      if (now.difference(_lastSendTime) >= minInterval) {
        _lastSendTime = now;
        await _sendPosition(geoPos);
      }
    } else {
      // Free-flight — send every position
      _currentZone = TrackingZone.normalFlight;
      await _sendPosition(geoPos);
    }

    // Landing detection
    _checkLandingConditions(geoPos);

    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Landing Detection
  // ═══════════════════════════════════════════════════════════════════════════

  void _checkLandingConditions(Position geoPos) {
    final now = DateTime.now();

    // Track recent altitudes (last 2 minutes) for relative altitude check
    _recentAltitudes.add(geoPos.altitude);
    _recentAltitudeTimes.add(now);
    while (_recentAltitudeTimes.isNotEmpty &&
        now.difference(_recentAltitudeTimes.first).inSeconds > 120) {
      _recentAltitudes.removeAt(0);
      _recentAltitudeTimes.removeAt(0);
    }

    // Find minimum altitude in last 2 minutes
    double minRecentAlt = geoPos.altitude;
    for (final alt in _recentAltitudes) {
      if (alt < minRecentAlt) minRecentAlt = alt;
    }

    // Landing conditions:
    // 1. Speed < 10 mph (4.47 m/s)
    // 2. Altitude within 100 ft (30.5m) of recent minimum
    final speedBelowThreshold = geoPos.speed < _landingSpeedMs;
    final nearMinAltitude =
        (geoPos.altitude - minRecentAlt).abs() < _landingAltToleranceM;

    if (speedBelowThreshold && nearMinAltitude) {
      // Conditions met — start or continue landing timer
      _landingDetectionStart ??= now;

      final detectionDuration = now.difference(_landingDetectionStart!);

      if (_landingCountdownActive) {
        // In countdown phase — check if countdown complete
        final countdownElapsed =
            now.difference(_landingCountdownStart!).inSeconds;
        if (countdownElapsed >= _landingCountdownSeconds) {
          // Landing confirmed — stop flight
          _onLandingConfirmed();
        }
        // (countdown continues — UI reads landingCountdownRemaining)
      } else if (detectionDuration.inSeconds >= _landingConfirmSeconds) {
        // Confirm phase complete — start countdown
        _landingCountdownActive = true;
        _landingCountdownStart = now;
        _error = 'Landing detected — stopping in ${_landingCountdownSeconds}s';
        notifyListeners();
      }
    } else {
      // Conditions broken — reset landing detection
      if (_landingDetectionStart != null || _landingCountdownActive) {
        _landingDetectionStart = null;
        _landingCountdownActive = false;
        _landingCountdownStart = null;
        if (_error?.startsWith('Landing detected') == true) {
          _error = null;
        }
        notifyListeners();
      }
    }
  }

  Future<void> _onLandingConfirmed() async {
    _landingCountdownActive = false;
    _landingCountdownStart = null;
    _landingDetectionStart = null;

    // Save flight duration before state change
    if (_trackingStartTime != null) {
      _flightDuration = DateTime.now().difference(_trackingStartTime!);
    }

    // Save the flight
    _flightTimer?.cancel();
    _flightTimer = null;
    await _saveCurrentFlight();

    // Check if we should enter monitoring mode
    if (_multiFlightEnabled && _isMonitoringEligible()) {
      _trackingState = TrackingState.monitoring;
      _error = null;

      // Update notification for monitoring mode
      BackgroundTrackingService.updateNotification(
        title: 'Aervyx — Monitoring',
        content: 'Watching for re-launch...',
      );

      // Switch to low-power GPS
      _startMonitoringGps();
      notifyListeners();
    } else {
      // Fully stop
      _locationSubscription?.cancel();
      _locationSubscription = null;
      _batteryCheckTimer?.cancel();
      _batteryCheckTimer = null;
      _trackingState = TrackingState.idle;
      _backendConnected = false;
      _activeTask = null;
      _currentZone = TrackingZone.stationary;
      _flightNumberToday = 0;
      notifyListeners();

      // Reset flight timer display after 3 seconds
      _flightResetTimer?.cancel();
      _flightResetTimer = Timer(const Duration(seconds: 3), () {
        _flightDuration = Duration.zero;
        _trackingStartTime = null;
        notifyListeners();
      });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Monitoring Mode
  // ═══════════════════════════════════════════════════════════════════════════

  bool _isMonitoringEligible() {
    final now = DateTime.now();

    // Must be before 20:00 local time
    if (now.hour >= 20) return false;

    // Battery must be above threshold
    if (_batteryThreshold != null &&
        _currentBatteryLevel != null &&
        _currentBatteryLevel! <= _batteryThreshold!) {
      return false;
    }

    // Must be within 1km of takeoff
    if (_takeoffLat != null &&
        _takeoffLon != null &&
        _lastPosition != null) {
      final dist = _haversineDistance(
        _takeoffLat!, _takeoffLon!,
        _lastPosition!.lat, _lastPosition!.lon,
      );
      if (dist > 1000) return false;
    }

    return true;
  }

  void _onMonitoringPositionUpdate(Position geoPos) {
    _updateLastPosition(geoPos);

    // Check takeoff detection (re-launch)
    _preFlightBuffer.add(geoPos);
    _preFlightBaseAltitude ??= geoPos.altitude;

    // Trim buffer
    while (_preFlightBuffer.length > 1) {
      final age = geoPos.timestamp.difference(_preFlightBuffer.first.timestamp);
      if (age.inSeconds > _preFlightBufferMaxSeconds) {
        _preFlightBuffer.removeAt(0);
      } else {
        break;
      }
    }

    // Update base altitude
    double minAlt = geoPos.altitude;
    for (final p in _preFlightBuffer) {
      if (p.altitude < minAlt) minAlt = p.altitude;
    }
    _preFlightBaseAltitude = minAlt;

    // Check takeoff
    final altGain = geoPos.altitude - _preFlightBaseAltitude!;
    final speed = geoPos.speed;
    final thresholds = _takeoffThresholds;

    final normalTakeoff = altGain >= thresholds.altitudeGainMeters &&
        speed > thresholds.speedThresholdMs;
    final strongAltTakeoff = altGain >= thresholds.altitudeGainMeters * 2;

    if (normalTakeoff || strongAltTakeoff) {
      // Re-launch detected — start new flight
      _flightNumberToday++;
      _monitoringTimer?.cancel();
      _monitoringTimer = null;

      _transitionToInFlight();

      // Switch back to full GPS stream
      _startGpsStream();
    }

    notifyListeners();
  }

  void _checkMonitoringConditions() {
    if (_trackingState != TrackingState.monitoring) return;

    final now = DateTime.now();

    // Auto-exit conditions (monitoring ONLY — never during inFlight)
    bool shouldExit = false;

    // Time > 20:00
    if (now.hour >= 20) shouldExit = true;

    // Battery below threshold
    if (_batteryThreshold != null &&
        _currentBatteryLevel != null &&
        _currentBatteryLevel! <= _batteryThreshold!) {
      shouldExit = true;
    }

    // Distance > 1km from takeoff
    if (_takeoffLat != null &&
        _takeoffLon != null &&
        _lastPosition != null) {
      final dist = _haversineDistance(
        _takeoffLat!, _takeoffLon!,
        _lastPosition!.lat, _lastPosition!.lon,
      );
      if (dist > 1000) shouldExit = true;
    }

    if (shouldExit) {
      _locationSubscription?.cancel();
      _locationSubscription = null;
      _monitoringTimer?.cancel();
      _monitoringTimer = null;
      _batteryCheckTimer?.cancel();
      _batteryCheckTimer = null;
      _trackingState = TrackingState.idle;
      _currentZone = TrackingZone.stationary;
      _flightNumberToday = 0;
      _error = 'Monitoring ended';
      notifyListeners();

      _flightResetTimer?.cancel();
      _flightResetTimer = Timer(const Duration(seconds: 3), () {
        _flightDuration = Duration.zero;
        _trackingStartTime = null;
        _error = null;
        notifyListeners();
      });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Position sending
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _sendPosition(Position geoPos) async {
    // Record trackpoint for IGC file
    _igc.addTrackPoint(geoPos);
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

      // Drain buffered positions (up to 20 per successful send)
      await _drainPositionBuffer();
    } on ApiException catch (e) {
      // Server IS reachable but rejected the request (4xx/5xx)
      _backendConnected = true;
      if (_positionBuffer.length < _maxBufferSize) {
        _positionBuffer.add(payload);
      }
      if (e.statusCode == 422) {
        _error = 'Position rejected (422) — backend update needed';
      } else if (e.statusCode == 401) {
        _error = 'Session expired — please log in again';
      } else {
        _error = 'Server error (${e.statusCode})';
      }
    } catch (e) {
      // Network-level failure — server unreachable
      _backendConnected = false;
      if (_positionBuffer.length < _maxBufferSize) {
        _positionBuffer.add(payload);
      }
      _error = 'Backend offline — recording locally'
          '${_positionBuffer.isNotEmpty ? ' (${_positionBuffer.length} buffered)' : ''}';
    }
  }

  /// Drain up to [limit] buffered positions to the backend.
  /// Stops on the first failure so we don't reorder or lose positions.
  Future<void> _drainPositionBuffer({int limit = 20}) async {
    var sent = 0;
    while (_positionBuffer.isNotEmpty && sent < limit) {
      final buffered = _positionBuffer.first;
      try {
        await _api.post(ApiConfig.trackPositionPath, body: buffered);
        _positionBuffer.removeAt(0);
        sent++;
      } catch (_) {
        // Backend went offline again — stop draining
        break;
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Flight saving
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _saveCurrentFlight() async {
    try {
      final trackPoints = _igc.currentTrackPointCount;
      _lastSavedIgcPath = await _igc.saveCurrentFlight(
        flightNumber: _flightNumberToday > 1 ? _flightNumberToday : null,
      );
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
  // Competition helpers
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _fetchActiveTask() async {
    try {
      final json = await _api.get(ApiConfig.activeTaskPath);
      if (json.containsKey('task_id')) {
        _activeTask = ActiveTask.fromJson(json);
      } else {
        _activeTask = null;
      }
    } catch (_) {
      _activeTask = null;
    }
  }

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

  /// Haversine distance in metres between two lat/lon points.
  static double _haversineDistance(
      double lat1, double lon1, double lat2, double lon2) {
    const earthRadius = 6371000.0;
    final dLat = _toRad(lat2 - lat1);
    final dLon = _toRad(lon2 - lon1);
    final a = sin(dLat / 2) * sin(dLat / 2) +
        cos(_toRad(lat1)) * cos(_toRad(lat2)) *
        sin(dLon / 2) * sin(dLon / 2);
    final c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }

  static double _toRad(double deg) => deg * pi / 180;

  // ═══════════════════════════════════════════════════════════════════════════
  // Flight timer & battery
  // ═══════════════════════════════════════════════════════════════════════════

  void _startFlightTimer() {
    _flightTimer?.cancel();
    _flightTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (_trackingStartTime != null &&
          _landingDetectionStart == null) {
        _flightDuration = DateTime.now().difference(_trackingStartTime!);

        // Update the foreground service notification with flight stats
        final h = _flightDuration.inHours;
        final m = _flightDuration.inMinutes % 60;
        final s = _flightDuration.inSeconds % 60;
        final timeStr = h > 0
            ? '${h}h ${m}m ${s}s'
            : '${m}m ${s}s';
        final altStr = _lastPosition?.alt != null
            ? '${_lastPosition!.alt!.toStringAsFixed(0)} m'
            : '--';
        BackgroundTrackingService.updateNotification(
          title: 'Aervyx — In Flight',
          content: '$timeStr  ·  Alt: $altStr  ·  $_positionCount pts',
        );

        notifyListeners();
      }
    });
  }

  void _startBatteryMonitor() {
    _checkBattery();
    _batteryCheckTimer?.cancel();
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
          _trackingState == TrackingState.inFlight) {
        // Battery low during flight — DON'T auto-stop flight.
        // Only warn. Flight can only end via landing detection or manual Stop.
        _error =
            'Low battery: $_currentBatteryLevel% (threshold: $_batteryThreshold%)';
      }
      notifyListeners();
    } catch (_) {
      // Battery level unavailable
    }
  }

  void _onLocationError(dynamic error) {
    _error = 'Location error: $error';

    // GPS signal lost — freeze landing detection timer
    if (_landingDetectionStart != null) {
      _landingDetectionStart = null;
      _landingCountdownActive = false;
      _landingCountdownStart = null;
    }

    notifyListeners();
  }

  @override
  void dispose() {
    stopTracking();
    _heartbeatTimer?.cancel();
    _batteryCheckTimer?.cancel();
    _flightTimer?.cancel();
    _adaptiveTimer?.cancel();
    _flightResetTimer?.cancel();
    _monitoringTimer?.cancel();
    super.dispose();
  }
}
