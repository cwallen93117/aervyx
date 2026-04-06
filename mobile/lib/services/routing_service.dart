import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../config/api_config.dart';
import '../models/driver_route.dart';
import 'api_service.dart';

/// Service managing driver routing: fetches optimized routes from the backend,
/// reports driver position, and tracks navigation progress.
class RoutingService extends ChangeNotifier {
  final ApiService _api;

  DriverRoute? _route;
  int _currentLegIndex = 0;
  int _currentManeuverIndex = 0;
  bool _navigating = false;
  bool _loading = false;
  String? _error;
  Timer? _positionTimer;
  int? _taskId;

  DriverRoute? get route => _route;
  int get currentLegIndex => _currentLegIndex;
  int get currentManeuverIndex => _currentManeuverIndex;
  bool get navigating => _navigating;
  bool get loading => _loading;
  String? get error => _error;

  /// Current maneuver instruction, if navigating.
  RouteManeuver? get currentManeuver {
    if (_route == null || !_navigating) return null;
    if (_currentLegIndex >= _route!.legs.length) return null;
    final leg = _route!.legs[_currentLegIndex];
    if (_currentManeuverIndex >= leg.maneuvers.length) return null;
    return leg.maneuvers[_currentManeuverIndex];
  }

  /// Current stop being navigated to.
  RouteStop? get currentStop {
    if (_route == null || !_navigating) return null;
    if (_currentLegIndex >= _route!.stops.length) return null;
    return _route!.stops[_currentLegIndex];
  }

  RoutingService(this._api);

  /// Fetch the optimized route from the backend.
  Future<void> fetchRoute(int taskId) async {
    _taskId = taskId;
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
      );

      final json = await _api.get(
        ApiConfig.driverRoutePath(taskId),
        query: {
          'lat': position.latitude.toString(),
          'lon': position.longitude.toString(),
        },
      );

      _route = DriverRoute.fromJson(json);
      _currentLegIndex = 0;
      _currentManeuverIndex = 0;
      _loading = false;
      _error = null;
      notifyListeners();
    } catch (e) {
      _loading = false;
      _error = 'Failed to get route: $e';
      notifyListeners();
    }
  }

  /// Start navigating the route — begins driver position reporting.
  void startNavigation(int taskId) {
    _taskId = taskId;
    _navigating = true;
    _currentLegIndex = 0;
    _currentManeuverIndex = 0;

    // Report driver position every 10 seconds
    _positionTimer?.cancel();
    _positionTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      _reportPosition();
    });
    _reportPosition(); // Immediate first report

    notifyListeners();
  }

  /// Stop navigating.
  void stopNavigation() {
    _navigating = false;
    _positionTimer?.cancel();
    _positionTimer = null;
    notifyListeners();
  }

  /// Advance to the next maneuver.
  void advanceManeuver() {
    if (_route == null) return;
    final leg = _route!.legs[_currentLegIndex];
    if (_currentManeuverIndex < leg.maneuvers.length - 1) {
      _currentManeuverIndex++;
    } else if (_currentLegIndex < _route!.legs.length - 1) {
      _currentLegIndex++;
      _currentManeuverIndex = 0;
    }
    notifyListeners();
  }

  /// Mark the current stop's pilot as picked up.
  Future<void> markPickedUp(int landingId) async {
    try {
      await _api.post(ApiConfig.driverPickupPath(landingId), body: {});

      // Advance to next leg
      if (_route != null && _currentLegIndex < _route!.stops.length) {
        _route!.stops[_currentLegIndex] = RouteStop(
          pilotId: _route!.stops[_currentLegIndex].pilotId,
          pilotName: _route!.stops[_currentLegIndex].pilotName,
          landingId: _route!.stops[_currentLegIndex].landingId,
          lat: _route!.stops[_currentLegIndex].lat,
          lon: _route!.stops[_currentLegIndex].lon,
          landedAt: _route!.stops[_currentLegIndex].landedAt,
          readyAt: _route!.stops[_currentLegIndex].readyAt,
          eta: _route!.stops[_currentLegIndex].eta,
          distanceKm: _route!.stops[_currentLegIndex].distanceKm,
          status: 'picked_up',
        );

        if (_currentLegIndex < _route!.legs.length - 1) {
          _currentLegIndex++;
          _currentManeuverIndex = 0;
        }
      }
      notifyListeners();

      // Re-optimize remaining route
      if (_taskId != null) {
        await fetchRoute(_taskId!);
      }
    } catch (e) {
      _error = 'Failed to mark pickup: $e';
      notifyListeners();
    }
  }

  /// Skip current stop — re-optimize without it.
  Future<void> skipCurrentStop() async {
    if (_taskId != null) {
      await fetchRoute(_taskId!);
    }
  }

  /// Force re-optimization with current position.
  Future<void> reoptimize() async {
    if (_taskId != null) {
      await fetchRoute(_taskId!);
    }
  }

  Future<void> _reportPosition() async {
    try {
      final position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(accuracy: LocationAccuracy.high),
      );
      await _api.post(ApiConfig.driverPositionPath, body: {
        'task_id': _taskId,
        'lat': position.latitude,
        'lon': position.longitude,
        'heading': position.heading,
        'speed': position.speed,
        'accuracy': position.accuracy,
        'timestamp': DateTime.now().toUtc().toIso8601String(),
      });
    } catch (_) {
      // Silent failure — position reporting is best-effort
    }
  }

  @override
  void dispose() {
    _positionTimer?.cancel();
    super.dispose();
  }
}
