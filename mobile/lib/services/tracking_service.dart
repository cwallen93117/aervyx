import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../config/api_config.dart';
import '../models/position.dart' as model;
import 'api_service.dart';

/// GPS tracking service — captures location in foreground, posts to backend.
class TrackingService extends ChangeNotifier {
  final ApiService _api;

  bool _isTracking = false;
  int? _activeTaskId;
  model.Position? _lastPosition;
  StreamSubscription<Position>? _locationSubscription;
  int _positionCount = 0;
  String? _error;

  bool get isTracking => _isTracking;
  int? get activeTaskId => _activeTaskId;
  model.Position? get lastPosition => _lastPosition;
  int get positionCount => _positionCount;
  String? get error => _error;

  TrackingService(this._api);

  /// Start GPS tracking for the given task.
  Future<void> startTracking(int taskId) async {
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

    _activeTaskId = taskId;
    _isTracking = true;
    _positionCount = 0;
    _error = null;
    notifyListeners();

    const locationSettings = LocationSettings(
      accuracy: LocationAccuracy.high,
      distanceFilter: 5, // metres — send update when moved >=5 m
    );

    _locationSubscription =
        Geolocator.getPositionStream(locationSettings: locationSettings)
            .listen(_onLocationUpdate, onError: _onLocationError);
  }

  /// Stop GPS tracking.
  void stopTracking() {
    _locationSubscription?.cancel();
    _locationSubscription = null;
    _isTracking = false;
    _activeTaskId = null;
    notifyListeners();
  }

  Future<void> _onLocationUpdate(Position geoPos) async {
    if (!_isTracking || _activeTaskId == null) return;

    final payload = {
      'task_id': _activeTaskId,
      'lat': geoPos.latitude,
      'lon': geoPos.longitude,
      'alt': geoPos.altitude,
      'speed': geoPos.speed,
      'heading': geoPos.heading,
      'accuracy': geoPos.accuracy,
      'timestamp': geoPos.timestamp.toUtc().toIso8601String(),
      'source': 'app',
    };

    try {
      final json = await _api.post(ApiConfig.trackPositionPath, body: payload);
      _lastPosition = model.Position.fromJson(json);
      _positionCount++;
      _error = null;
    } catch (e) {
      _error = 'Failed to send position: $e';
    }
    notifyListeners();
  }

  void _onLocationError(dynamic error) {
    _error = 'Location error: $error';
    notifyListeners();
  }

  /// Connect to SSE stream for live positions on a task.
  Stream<List<model.Position>> livePositionStream(int taskId) async* {
    final Map<int, model.Position> latestByPilot = {};

    await for (final line
        in _api.sseStream(ApiConfig.livePositionsPath(taskId))) {
      if (line.startsWith('data: ')) {
        final data = line.substring(6);
        try {
          final decoded = jsonDecode(data);
          if (decoded is List) {
            // snapshot event
            for (final item in decoded) {
              final pos =
                  model.Position.fromJson(item as Map<String, dynamic>);
              if (pos.pilotId != null) {
                latestByPilot[pos.pilotId!] = pos;
              }
            }
          } else if (decoded is Map<String, dynamic>) {
            // single position event
            final pos = model.Position.fromJson(decoded);
            if (pos.pilotId != null) {
              latestByPilot[pos.pilotId!] = pos;
            }
          }
          yield latestByPilot.values.toList();
        } catch (_) {
          // Skip malformed data lines
        }
      }
    }
  }

  @override
  void dispose() {
    stopTracking();
    super.dispose();
  }
}
