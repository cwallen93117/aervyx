import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:battery_plus/battery_plus.dart';
import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:path_provider/path_provider.dart';

import '../config/api_config.dart';
import '../models/position.dart' as model;
import '../models/turnpoint.dart';
import 'api_service.dart';
import 'auth_service.dart';
import 'background_service.dart';
import 'igc_service.dart';
import 'persistent_runtime_service.dart';

typedef TrackingSessionDirectoryProvider = Future<Directory> Function();

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

/// Severity level for tracking notifications (flight save results, etc.).
enum NotificationLevel { success, warning, error }

/// Sport type — determines takeoff detection thresholds.
enum SportType { paraglider, hangGlider, glider }

@visibleForTesting
class TrackingSessionSnapshot {
  final TrackingState trackingState;
  final DateTime savedAt;
  final DateTime? trackingStartTime;
  final int positionCount;
  final int flightNumberToday;
  final double? takeoffLat;
  final double? takeoffLon;
  final bool driverMode;
  final bool debugMode;
  final bool multiFlightEnabled;
  final model.Position? lastPosition;

  const TrackingSessionSnapshot({
    required this.trackingState,
    required this.savedAt,
    required this.trackingStartTime,
    required this.positionCount,
    required this.flightNumberToday,
    required this.takeoffLat,
    required this.takeoffLon,
    required this.driverMode,
    required this.debugMode,
    required this.multiFlightEnabled,
    required this.lastPosition,
  });

  bool get isRestorable =>
      trackingState == TrackingState.preFlight ||
      trackingState == TrackingState.inFlight ||
      trackingState == TrackingState.monitoring;

  bool isStale(DateTime now) => now.difference(savedAt).inHours >= 18;

  Map<String, dynamic> toJson() => {
        'trackingState': trackingState.name,
        'savedAt': savedAt.toUtc().toIso8601String(),
        if (trackingStartTime != null)
          'trackingStartTime': trackingStartTime!.toUtc().toIso8601String(),
        'positionCount': positionCount,
        'flightNumberToday': flightNumberToday,
        if (takeoffLat != null) 'takeoffLat': takeoffLat,
        if (takeoffLon != null) 'takeoffLon': takeoffLon,
        'driverMode': driverMode,
        'debugMode': debugMode,
        'multiFlightEnabled': multiFlightEnabled,
        if (lastPosition != null) 'lastPosition': lastPosition!.toJson(),
      };

  static TrackingSessionSnapshot fromJson(Map<String, dynamic> json) {
    final stateName = json['trackingState'] as String?;
    final state = TrackingState.values
        .where((value) => value.name == stateName)
        .firstOrNull;
    if (state == null) {
      throw const FormatException('Unknown tracking state');
    }

    final lastPositionJson = json['lastPosition'];
    return TrackingSessionSnapshot(
      trackingState: state,
      savedAt: DateTime.parse(json['savedAt'] as String).toUtc(),
      trackingStartTime: json['trackingStartTime'] == null
          ? null
          : DateTime.parse(json['trackingStartTime'] as String).toUtc(),
      positionCount: (json['positionCount'] as num?)?.toInt() ?? 0,
      flightNumberToday: (json['flightNumberToday'] as num?)?.toInt() ?? 0,
      takeoffLat: (json['takeoffLat'] as num?)?.toDouble(),
      takeoffLon: (json['takeoffLon'] as num?)?.toDouble(),
      driverMode: json['driverMode'] == true,
      debugMode: json['debugMode'] == true,
      multiFlightEnabled: json['multiFlightEnabled'] != false,
      lastPosition: lastPositionJson is Map<String, dynamic>
          ? _positionFromSnapshotJson(lastPositionJson)
          : null,
    );
  }

  static model.Position _positionFromSnapshotJson(Map<String, dynamic> json) {
    return model.Position(
      lat: (json['lat'] as num).toDouble(),
      lon: (json['lon'] as num).toDouble(),
      alt: (json['alt'] as num?)?.toDouble(),
      speed: (json['speed'] as num?)?.toDouble(),
      heading: (json['heading'] as num?)?.toDouble(),
      accuracy: (json['accuracy'] as num?)?.toDouble(),
      timestamp: DateTime.parse(json['timestamp'] as String).toUtc(),
      source: json['source'] as String?,
      deviceId: json['device_id'] as String?,
      batteryLevel: json['battery_level'] as int?,
    );
  }
}

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
  final AuthService _auth;
  final IgcService _igc;
  final TrackingSessionDirectoryProvider _sessionDirectoryProvider;
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
  Timer? _positionHeartbeatTimer;
  int _positionCount = 0;
  String? _error;
  NotificationLevel _notificationLevel = NotificationLevel.error;
  bool _backendConnected = false;
  Timer? _heartbeatTimer;

  // ── Stationary heartbeat ──
  /// Timestamp of the last position received from the GPS stream.
  /// Used by the heartbeat timer to decide when to re-send a synthesised fix.
  DateTime _lastStreamPositionAt = DateTime.fromMillisecondsSinceEpoch(0);

  // ── Offline position buffer ──
  final List<Map<String, dynamic>> _positionBuffer = [];
  static const int _maxBufferSize = 5000;

  // ── Battery protection ──
  int? _batteryThreshold = 15;
  int? _currentBatteryLevel;
  DateTime? _currentBatteryLevelSeenAt;
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
  bool _debugMode = false;
  bool _driverMode = false;

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
      _adminTakeoffThresholds ?? _defaultTakeoffThresholds[_sportType]!;

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
  bool get isTracking => _trackingState != TrackingState.idle;
  bool get isInFlight => _trackingState == TrackingState.inFlight;
  bool get isPreFlight => _trackingState == TrackingState.preFlight;
  bool get isMonitoring => _trackingState == TrackingState.monitoring;
  TrackingState get trackingState => _trackingState;
  model.Position? get lastPosition => _lastPosition;
  int get positionCount => _positionCount;
  String? get error => _error;
  NotificationLevel get notificationLevel => _notificationLevel;
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
  bool get debugMode => _debugMode;
  bool get driverMode => _driverMode;
  bool get isDriverTracking =>
      _driverMode && _trackingState == TrackingState.inFlight;
  int get bufferedPositionCount => _positionBuffer.length;
  bool get landingCountdownActive => _landingCountdownActive;

  /// True when landing conditions are detected but not yet confirmed.
  bool get landingDetected =>
      _landingDetectionStart != null &&
      _trackingState == TrackingState.inFlight;
  int get landingCountdownRemaining {
    if (!_landingCountdownActive || _landingCountdownStart == null) return 0;
    final elapsed =
        DateTime.now().difference(_landingCountdownStart!).inSeconds;
    return max(0, _landingCountdownSeconds - elapsed);
  }

  /// Path to the last saved IGC file (shown briefly after stop).
  String? _lastSavedIgcPath;
  String? get lastSavedIgcPath => _lastSavedIgcPath;

  @visibleForTesting
  void debugSetCurrentBatteryLevel(int? level) {
    _currentBatteryLevel = level;
    _currentBatteryLevelSeenAt = level == null ? null : DateTime.now().toUtc();
  }

  TrackingService(
    this._api,
    this._auth,
    this._igc, {
    TrackingSessionDirectoryProvider? sessionDirectoryProvider,
  }) : _sessionDirectoryProvider =
            sessionDirectoryProvider ?? getApplicationDocumentsDirectory {
    // Start server heartbeat immediately so the LED shows status on app open
    _startHeartbeat();
    // Retry any pending IGC uploads from previous sessions
    _retryPendingUploads();
  }

  Future<File> _trackingSessionFile() async {
    final dir = await _sessionDirectoryProvider();
    return File('${dir.path}/tracking_session.json');
  }

  TrackingSessionSnapshot _buildSessionSnapshot() {
    return TrackingSessionSnapshot(
      trackingState: _trackingState,
      savedAt: DateTime.now().toUtc(),
      trackingStartTime: _trackingStartTime,
      positionCount: _positionCount,
      flightNumberToday: _flightNumberToday,
      takeoffLat: _takeoffLat,
      takeoffLon: _takeoffLon,
      driverMode: _driverMode,
      debugMode: _debugMode,
      multiFlightEnabled: _multiFlightEnabled,
      lastPosition: _lastPosition,
    );
  }

  Future<void> _persistTrackingSession() async {
    if (_trackingState == TrackingState.idle) {
      await _clearTrackingSession();
      return;
    }
    final file = await _trackingSessionFile();
    await file.writeAsString(jsonEncode(_buildSessionSnapshot().toJson()));
  }

  void _schedulePersistTrackingSession() {
    unawaited(_persistTrackingSession());
  }

  Future<void> _clearTrackingSession() async {
    final file = await _trackingSessionFile();
    if (await file.exists()) {
      await file.delete();
    }
  }

  Future<TrackingSessionSnapshot?> _loadTrackingSession() async {
    final file = await _trackingSessionFile();
    if (!await file.exists()) return null;
    try {
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! Map<String, dynamic>) {
        throw const FormatException('Tracking session is not an object');
      }
      final snapshot = TrackingSessionSnapshot.fromJson(decoded);
      if (!snapshot.isRestorable || snapshot.isStale(DateTime.now().toUtc())) {
        await _clearTrackingSession();
        return null;
      }
      return snapshot;
    } catch (_) {
      await _clearTrackingSession();
      return null;
    }
  }

  @visibleForTesting
  Future<void> debugSaveTrackingSessionSnapshot(
    TrackingSessionSnapshot snapshot,
  ) async {
    final file = await _trackingSessionFile();
    await file.writeAsString(jsonEncode(snapshot.toJson()));
  }

  @visibleForTesting
  Future<void> debugWriteRawTrackingSession(String content) async {
    final file = await _trackingSessionFile();
    await file.writeAsString(content);
  }

  @visibleForTesting
  Future<bool> debugTrackingSessionExists() async {
    final file = await _trackingSessionFile();
    return file.exists();
  }

  Future<void> restoreActiveSession({
    bool restartRuntimeServices = true,
  }) async {
    final snapshot = await _loadTrackingSession();
    if (snapshot == null) return;

    if (restartRuntimeServices) {
      final permissionReady = await _ensureLocationPermission();
      if (!permissionReady) {
        await _clearTrackingSession();
        _error = 'Location permission required to resume tracking';
        notifyListeners();
        return;
      }
    }

    _flightResetTimer?.cancel();
    _flightResetTimer = null;
    _monitoringTimer?.cancel();
    _monitoringTimer = null;
    _positionHeartbeatTimer?.cancel();
    _positionHeartbeatTimer = null;

    _trackingState = snapshot.trackingState;
    _trackingStartTime = snapshot.trackingStartTime;
    _positionCount = snapshot.positionCount;
    _flightNumberToday = snapshot.flightNumberToday;
    _takeoffLat = snapshot.takeoffLat;
    _takeoffLon = snapshot.takeoffLon;
    _driverMode = snapshot.driverMode;
    _debugMode = snapshot.debugMode;
    _multiFlightEnabled = snapshot.multiFlightEnabled;
    _lastPosition = snapshot.lastPosition;
    _error = null;
    _stoppedByBattery = false;

    if (_trackingStartTime != null) {
      _flightDuration = DateTime.now().difference(_trackingStartTime!);
    }

    notifyListeners();

    if (!restartRuntimeServices) return;

    await _fetchActiveTask();
    await fetchFlightDetectionSettings();
    unawaited(PersistentRuntimeService.setLocationActive(true));

    if (_trackingState == TrackingState.monitoring) {
      BackgroundTrackingService.updateNotification(
        title: 'Aervyx - Monitoring',
        content: 'Watching for re-launch...',
      );
      _startMonitoringGps();
    } else {
      if (_trackingState == TrackingState.inFlight) {
        _startFlightTimer();
        BackgroundTrackingService.updateNotification(
          title: _driverMode ? 'Aervyx - Driver Mode' : 'Aervyx - In Flight',
          content: _driverMode
              ? 'Relaying driver position...'
              : 'Resuming flight...',
        );
      } else {
        BackgroundTrackingService.updateNotification(
          title: 'Aervyx - Pre-Flight',
          content: 'Waiting for takeoff...',
        );
      }
      _startGpsStream();
      _startPositionHeartbeat();
    }

    try {
      await BackgroundTrackingService.start();
    } catch (_) {
      // Background service unavailable; foreground tracking still resumes.
    }
    _startBatteryMonitor();
    _schedulePersistTrackingSession();
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

  /// Enable/disable debug mode — skips flight detection, sends every position.
  ///
  /// If tracking is already active, restarts the GPS stream (to pick up the
  /// new distanceFilter) and restarts the heartbeat timer (to use the new
  /// 1 s / 5 s cadence) so the change takes effect without a full restart.
  void setDebugMode(bool enabled) {
    _debugMode = enabled;
    if (_trackingState == TrackingState.preFlight ||
        _trackingState == TrackingState.inFlight) {
      _startGpsStream();
      _startPositionHeartbeat();
    }
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
      _landingSpeedMs =
          (config['landing_speed_mph'] as num).toDouble() * 0.44704;
    }
    if (config.containsKey('landing_alt_tolerance_ft')) {
      _landingAltToleranceM =
          (config['landing_alt_tolerance_ft'] as num).toDouble() * 0.3048;
    }
    if (config.containsKey('landing_confirm_seconds')) {
      _landingConfirmSeconds =
          (config['landing_confirm_seconds'] as num).toInt();
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

  Future<bool> _ensureLocationPermission() async {
    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied) {
      _error = 'Location permission denied';
      notifyListeners();
      return false;
    }
    if (permission == LocationPermission.deniedForever) {
      _error = 'Location permission permanently denied. Enable in settings.';
      notifyListeners();
      return false;
    }
    return true;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Start / Stop / Force-Start
  // ═══════════════════════════════════════════════════════════════════════════

  /// Start GPS tracking — enters preFlight and waits for takeoff detection.
  Future<void> startTracking() async {
    if (_trackingState != TrackingState.idle &&
        _trackingState != TrackingState.monitoring) {
      return;
    }

    if (!await _ensureLocationPermission()) return;

    _flightResetTimer?.cancel();
    _flightResetTimer = null;
    _monitoringTimer?.cancel();
    _monitoringTimer = null;

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
    _driverMode = _driverMode || _auth.user?.profileType == 'driver';

    if (_flightNumberToday == 0) {
      _flightNumberToday = 1;
    }

    if (_driverMode) {
      _trackingState = TrackingState.inFlight;
      _trackingStartTime = DateTime.now();
      _currentZone = TrackingZone.normalFlight;
      _startFlightTimer();
      BackgroundTrackingService.updateNotification(
        title: 'Aervyx - Driver Mode',
        content: 'Relaying driver position...',
      );
    } else if (_debugMode) {
      // Debug mode — skip pre-flight, go straight to recording + sending
      _trackingState = TrackingState.inFlight;
      _trackingStartTime = DateTime.now();
      _startFlightTimer();
      BackgroundTrackingService.updateNotification(
        title: 'Aervyx — Debug Mode',
        content: 'Sending all positions to server...',
      );
    } else {
      _trackingState = TrackingState.preFlight;
      // Update notification for pre-flight state
      BackgroundTrackingService.updateNotification(
        title: 'Aervyx — Pre-Flight',
        content: 'Waiting for takeoff...',
      );
    }

    unawaited(PersistentRuntimeService.setLocationActive(true));
    _schedulePersistTrackingSession();
    notifyListeners();

    // Fetch settings from backend
    await _fetchActiveTask();
    await fetchFlightDetectionSettings();

    // Start GPS stream
    _startGpsStream();

    // Heartbeat: sends a synthesised fix every 5 s when the GPS stream is
    // silent (stationary pilot at launch, slow thermalling, ground testing)
    _startPositionHeartbeat();

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
  Future<void> startDriverTracking() async {
    if (_trackingState != TrackingState.idle &&
        _trackingState != TrackingState.monitoring) {
      return;
    }
    _driverMode = true;
    await startTracking();
    if (_trackingState == TrackingState.idle) {
      _driverMode = false;
    }
  }

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
    final wasDriverMode = _driverMode;

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
    _positionHeartbeatTimer?.cancel();
    _positionHeartbeatTimer = null;
    _landingCountdownActive = false;
    _landingCountdownStart = null;

    // Keep final flight duration
    if (_trackingStartTime != null) {
      _flightDuration = DateTime.now().difference(_trackingStartTime!);
    }

    _trackingState = TrackingState.idle;
    unawaited(PersistentRuntimeService.setLocationActive(false));
    _backendConnected = false;
    _activeTask = null;
    _currentZone = TrackingZone.stationary;
    _flightNumberToday = 0;
    _driverMode = false;
    await _clearTrackingSession();

    // Stop background foreground service
    try {
      await BackgroundTrackingService.stop();
    } catch (_) {
      // Background service was not running
    }

    notifyListeners();

    // Save flight if we were recording
    if (wasInFlight && !wasDriverMode) {
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

    if (_driverMode) {
      const settings = LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 0,
      );
      _locationSubscription =
          Geolocator.getPositionStream(locationSettings: settings)
              .listen(_onPositionUpdate, onError: _onLocationError);
    } else if (_activeTask != null) {
      // Competition mode — high-accuracy, 0 distance filter
      const settings = LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: 0,
      );
      _locationSubscription =
          Geolocator.getPositionStream(locationSettings: settings)
              .listen(_onPositionUpdate, onError: _onLocationError);
    } else if (_debugMode) {
      // Debug mode — fire on every GPS sample regardless of movement
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

  /// Start a position heartbeat that synthesises a position update when the
  /// GPS stream is silent.
  ///
  /// Normal mode: fires every 5 s, skipped if the GPS stream emitted within
  /// the last 5 s (pilot is moving — stream is already delivering points).
  ///
  /// Debug mode: fires every 1 s with NO freshness guard so at least one
  /// position is always sent per second, even when the GPS stream is active.
  /// This guarantees a continuous flow for pipeline testing.
  void _startPositionHeartbeat() {
    _positionHeartbeatTimer?.cancel();
    final interval =
        _debugMode ? const Duration(seconds: 1) : const Duration(seconds: 5);
    _positionHeartbeatTimer = Timer.periodic(interval, (_) async {
      if (_trackingState != TrackingState.preFlight &&
          _trackingState != TrackingState.inFlight) {
        return;
      }
      if (!_debugMode) {
        // Normal mode: skip if the GPS stream fired recently
        final silentFor = DateTime.now().difference(_lastStreamPositionAt);
        if (silentFor.inSeconds < 5) {
          return;
        }
      }
      if (_lastPosition == null) return;

      // Build a synthetic Geolocator Position from the last known fix,
      // with a fresh timestamp so the server records the current time.
      // Nullable fields in the model are coalesced to 0.0 — the same
      // sentinel value Geolocator uses when a measurement is unavailable.
      final last = _lastPosition!;
      final synthetic = Position(
        latitude: last.lat,
        longitude: last.lon,
        altitude: last.alt ?? 0.0,
        altitudeAccuracy: 0.0,
        speed: last.speed ?? 0.0,
        heading: last.heading ?? 0.0,
        accuracy: last.accuracy ?? 0.0,
        headingAccuracy: 0.0,
        speedAccuracy: 0.0,
        timestamp: DateTime.now().toUtc(),
      );
      await _onPositionUpdate(synthetic);
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // Position Handling — unified callback
  // ═══════════════════════════════════════════════════════════════════════════

  /// Track last time we sent a position — used to throttle sends per zone.
  DateTime _lastSendTime = DateTime.fromMillisecondsSinceEpoch(0);

  Future<void> _onPositionUpdate(Position geoPos) async {
    // Record when the GPS stream last fired — heartbeat uses this to avoid
    // double-sending when the device is actually moving.
    _lastStreamPositionAt = DateTime.now();

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

    // Flush pre-flight buffer into IGC recording.
    // Note: these points are written to the IGC file but NOT sent to the
    // server, so we deliberately do NOT increment _positionCount here.
    // The counter reflects points actually sent to the server.
    for (final pos in _preFlightBuffer) {
      _igc.addTrackPoint(pos);
    }
    _preFlightBuffer.clear();

    // Start flight timer
    _startFlightTimer();

    // Reset landing detection
    _landingDetectionStart = null;
    _landingCountdownActive = false;
    _recentAltitudes.clear();
    _recentAltitudeTimes.clear();

    _schedulePersistTrackingSession();
    notifyListeners();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // In-Flight — recording + landing detection
  // ═══════════════════════════════════════════════════════════════════════════

  Future<void> _handleInFlight(Position geoPos) async {
    if (_driverMode) {
      _currentZone = TrackingZone.normalFlight;
      await _sendPosition(geoPos, recordIgc: false);
      notifyListeners();
      return;
    }

    // Debug mode — send every position at 1Hz, skip landing detection
    if (_debugMode) {
      _currentZone = TrackingZone.normalFlight;
      await _sendPosition(geoPos);
      notifyListeners();
      return;
    }

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
    // Heartbeat no longer needed once we leave inFlight
    _positionHeartbeatTimer?.cancel();
    _positionHeartbeatTimer = null;
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
      _schedulePersistTrackingSession();
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
      unawaited(_clearTrackingSession());
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
    if (_takeoffLat != null && _takeoffLon != null && _lastPosition != null) {
      final dist = _haversineDistance(
        _takeoffLat!,
        _takeoffLon!,
        _lastPosition!.lat,
        _lastPosition!.lon,
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
    if (_takeoffLat != null && _takeoffLon != null && _lastPosition != null) {
      final dist = _haversineDistance(
        _takeoffLat!,
        _takeoffLon!,
        _lastPosition!.lat,
        _lastPosition!.lon,
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
      unawaited(_clearTrackingSession());
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

  Future<void> _sendPosition(Position geoPos, {bool recordIgc = true}) async {
    if (recordIgc) {
      _igc.addTrackPoint(geoPos);
    }
    _positionCount++;

    // Try to send to backend (non-blocking for UI)
    final payload = debugBuildPositionPayload(geoPos);

    try {
      await _api.post(ApiConfig.trackPositionPath, body: payload);
      _error = null;
      _backendConnected = true;

      // Drain buffered positions (up to 20 per successful send)
      await _drainPositionBuffer();

      // Connectivity confirmed — retry any pending IGC uploads
      _retryPendingUploads();
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

  @visibleForTesting
  Map<String, dynamic> debugBuildPositionPayload(Position geoPos) {
    return debugBuildPositionPayloadFromValues(
      geoPos,
      taskId: _activeTask?.taskId,
      batteryLevel: _currentBatteryLevel,
      batteryLevelSeenAt: _currentBatteryLevelSeenAt,
      zone: _currentZone,
    );
  }

  @visibleForTesting
  static Map<String, dynamic> debugBuildPositionPayloadFromValues(
    Position geoPos, {
    int? taskId,
    int? batteryLevel,
    DateTime? batteryLevelSeenAt,
    TrackingZone zone = TrackingZone.stationary,
  }) {
    return {
      'lat': geoPos.latitude,
      'lon': geoPos.longitude,
      'alt': geoPos.altitude,
      'speed': geoPos.speed,
      'heading': geoPos.heading,
      'accuracy': geoPos.accuracy,
      'timestamp': geoPos.timestamp.toUtc().toIso8601String(),
      'source': 'app',
      if (taskId != null) 'task_id': taskId,
      if (batteryLevel != null) 'battery_level': batteryLevel,
      if (batteryLevel != null && batteryLevelSeenAt != null)
        'battery_level_seen_at': batteryLevelSeenAt.toUtc().toIso8601String(),
      'zone': zone.name,
    };
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
    // Capture task reference before save — it could be cleared during state transitions
    final taskId = _activeTask?.taskId;

    try {
      final trackPoints = _igc.currentTrackPointCount;
      _lastSavedIgcPath = await _igc.saveCurrentFlight(
        pilotName: _auth.user?.fullName,
        flightNumber: _flightNumberToday > 0 ? _flightNumberToday : null,
      );
      if (_lastSavedIgcPath != null) {
        _error = 'Flight saved ($trackPoints points)';
        _notificationLevel = NotificationLevel.success;
      } else {
        _error = 'Flight too short to save ($trackPoints points recorded)';
        _notificationLevel = NotificationLevel.warning;
      }
    } catch (e) {
      _lastSavedIgcPath = null;
      _error = 'Failed to save flight: $e';
      _notificationLevel = NotificationLevel.error;
    }
    notifyListeners();

    // Best-effort upload to backend — fire and forget
    if (_lastSavedIgcPath != null) {
      _uploadIgcFile(_lastSavedIgcPath!, taskId);
    }
  }

  /// Upload IGC file to the backend, queuing for retry on failure.
  Future<void> _uploadIgcFile(String filePath, int? taskId) async {
    final success = await _attemptUpload(filePath, taskId);
    if (!success) {
      await _enqueueUpload(filePath, taskId);
    }
  }

  /// Attempt a single upload. Returns true on success.
  Future<bool> _attemptUpload(String filePath, int? taskId) async {
    try {
      if (!File(filePath).existsSync())
        return true; // file gone, nothing to upload
      if (taskId != null) {
        await _api.uploadFile(
          ApiConfig.taskUploadPath(taskId),
          filePath: filePath,
          fields: {'upload_source': 'app'},
        );
      } else {
        await _api.uploadFile(
          ApiConfig.logbookUploadPath,
          filePath: filePath,
        );
      }
      return true;
    } catch (e) {
      debugPrint('IGC upload failed: $e');
      return false;
    }
  }

  // ── Persistent upload retry queue ──

  bool _retrying = false;

  Future<File> _uploadQueueFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/pending_uploads.json');
  }

  Future<List<Map<String, dynamic>>> _loadQueue() async {
    try {
      final file = await _uploadQueueFile();
      if (!file.existsSync()) return [];
      final content = await file.readAsString();
      if (content.trim().isEmpty) return [];
      return (jsonDecode(content) as List).cast<Map<String, dynamic>>();
    } catch (_) {
      return [];
    }
  }

  Future<void> _saveQueue(List<Map<String, dynamic>> queue) async {
    final file = await _uploadQueueFile();
    await file.writeAsString(jsonEncode(queue));
  }

  Future<void> _enqueueUpload(String filePath, int? taskId) async {
    final queue = await _loadQueue();
    // Don't add duplicates
    if (queue.any((e) => e['filePath'] == filePath)) return;
    queue.add({'filePath': filePath, 'taskId': taskId});
    await _saveQueue(queue);
    debugPrint('IGC upload queued for retry: $filePath');
  }

  /// Retry all pending uploads. Called on app startup and after
  /// successful position sends confirm connectivity.
  Future<void> _retryPendingUploads() async {
    if (_retrying) return;
    _retrying = true;
    try {
      final queue = await _loadQueue();
      if (queue.isEmpty) return;
      final remaining = <Map<String, dynamic>>[];
      for (final entry in queue) {
        final filePath = entry['filePath'] as String;
        final taskId = entry['taskId'] as int?;
        final success = await _attemptUpload(filePath, taskId);
        if (!success) {
          remaining.add(entry);
        } else {
          debugPrint('IGC upload retry succeeded: $filePath');
        }
      }
      await _saveQueue(remaining);
    } finally {
      _retrying = false;
    }
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
        cos(_toRad(lat1)) * cos(_toRad(lat2)) * sin(dLon / 2) * sin(dLon / 2);
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
      if (_trackingStartTime != null && _landingDetectionStart == null) {
        _flightDuration = DateTime.now().difference(_trackingStartTime!);

        // Update the foreground service notification with flight stats
        final h = _flightDuration.inHours;
        final m = _flightDuration.inMinutes % 60;
        final s = _flightDuration.inSeconds % 60;
        final timeStr = h > 0 ? '${h}h ${m}m ${s}s' : '${m}m ${s}s';
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
      _currentBatteryLevelSeenAt = DateTime.now().toUtc();
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
    _locationSubscription?.cancel();
    _heartbeatTimer?.cancel();
    _batteryCheckTimer?.cancel();
    _flightTimer?.cancel();
    _adaptiveTimer?.cancel();
    _flightResetTimer?.cancel();
    _monitoringTimer?.cancel();
    _positionHeartbeatTimer?.cancel();
    super.dispose();
  }
}
