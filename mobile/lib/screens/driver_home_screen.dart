import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/auth_service.dart';
import '../services/driver_service.dart';
import '../services/tracking_service.dart';
import '../utils/app_shutdown.dart';
import '../widgets/live_map_style.dart';
import '../widgets/map_scale_bar.dart';
import 'driver_navigation_screen.dart';
import 'settings_screen.dart';

/// Full-screen driver map with always-on driver tracking and pickup actions.
class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({super.key});

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  final MapController _mapController = MapController();
  DriverService? _driverService;
  TrackingService? _trackingService;
  LiveMapStyle _mapStyle = LiveMapStyle.map;
  bool _initialCenterDone = false;
  bool _userPanned = false;
  bool _followDriver = true;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<DriverService>().connect();
      _ensureDriverTracking();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _driverService = context.read<DriverService>();
    final tracking = context.read<TrackingService>();
    if (_trackingService == tracking) return;
    _trackingService?.removeListener(_handleTrackingUpdate);
    _trackingService = tracking;
    _trackingService?.addListener(_handleTrackingUpdate);
  }

  @override
  void dispose() {
    _trackingService?.removeListener(_handleTrackingUpdate);
    _driverService?.disconnect();
    super.dispose();
  }

  Future<void> _ensureDriverTracking() async {
    final tracking = context.read<TrackingService>();
    if (tracking.isDriverTracking) return;
    try {
      await tracking.startDriverTracking();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Driver tracking will start when GPS is available'),
          duration: Duration(seconds: 3),
        ),
      );
    }
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

  void _moveToDriver(LatLng target) {
    _mapController.move(target, _followZoom());
  }

  void _handleTrackingUpdate() {
    if (!_followDriver || !mounted) return;
    final position = _trackingService?.lastPosition;
    if (position == null) return;
    _initialCenterDone = true;
    _moveToDriver(LatLng(position.lat, position.lon));
  }

  void _centerOnDriver() {
    final position = context.read<TrackingService>().lastPosition;
    if (position != null) {
      setState(() {
        _userPanned = false;
        _followDriver = true;
      });
      _moveToDriver(LatLng(position.lat, position.lon));
      return;
    }

    setState(() {
      _userPanned = false;
      _followDriver = true;
    });
    _ensureDriverTracking();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('No GPS fix yet - waiting for location'),
        duration: Duration(seconds: 2),
      ),
    );
  }

  void _centerInitialMapIfNeeded() {
    if (_initialCenterDone || _userPanned) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _initialCenterDone || _userPanned) return;
      final driverPosition = context.read<TrackingService>().lastPosition;
      final pilots = context.read<DriverService>().visiblePilots;
      final LatLng? target = driverPosition != null
          ? LatLng(driverPosition.lat, driverPosition.lon)
          : pilots.isNotEmpty
              ? LatLng(pilots.first.lat, pilots.first.lon)
              : null;
      if (target == null) return;
      _initialCenterDone = true;
      _mapController.move(target, 12);
    });
  }

  /// Open Google Maps navigation to the pilot's position.
  Future<void> _navigateToPilot(DriverPilot pilot) async {
    final uri = Uri.parse(
      'google.navigation:q=${pilot.lat},${pilot.lon}&mode=d',
    );

    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
    } else {
      final geoUri = Uri.parse(
        'geo:${pilot.lat},${pilot.lon}?q=${pilot.lat},${pilot.lon}',
      );
      if (await canLaunchUrl(geoUri)) {
        await launchUrl(geoUri);
      } else if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('No navigation app found')),
        );
      }
    }
  }

  String _timeSince(DateTime value) {
    final ago = DateTime.now().difference(value);
    if (ago.inSeconds < 10) return 'now';
    if (ago.inSeconds < 60) return '${ago.inSeconds}s ago';
    if (ago.inMinutes < 60) return '${ago.inMinutes}m ago';
    return '${ago.inHours}h ago';
  }

  void _showPilotSheet(DriverPilot pilot) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (sheetContext) {
        final theme = Theme.of(sheetContext);
        return Padding(
          padding: EdgeInsets.fromLTRB(
            20,
            0,
            20,
            20 + MediaQuery.of(sheetContext).padding.bottom,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      pilot.compNumber != null
                          ? '#${pilot.compNumber} ${pilot.name}'
                          : pilot.name,
                      style: theme.textTheme.titleLarge,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  _PilotStatusBadge(pilot: pilot),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 14,
                runSpacing: 8,
                children: [
                  _PilotMetric(
                    icon: Icons.schedule,
                    label: 'Last seen',
                    value: _timeSince(pilot.lastSeen),
                  ),
                  if (pilot.alt != null)
                    _PilotMetric(
                      icon: Icons.height,
                      label: 'Altitude',
                      value: '${pilot.alt!.toStringAsFixed(0)} m',
                    ),
                  if (pilot.speed != null)
                    _PilotMetric(
                      icon: Icons.speed,
                      label: 'Speed',
                      value: '${(pilot.speed! * 3.6).toStringAsFixed(0)} km/h',
                    ),
                ],
              ),
              const SizedBox(height: 18),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  icon: const Icon(Icons.navigation),
                  label: const Text('Navigate'),
                  onPressed: () {
                    Navigator.of(sheetContext).pop();
                    unawaited(_navigateToPilot(pilot));
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final driver = context.watch<DriverService>();
    final auth = context.watch<AuthService>();
    final tracking = context.watch<TrackingService>();
    final theme = Theme.of(context);
    final pilots = driver.visiblePilots;
    final driverPosition = tracking.lastPosition;
    final hasActiveTask = driver.hasActiveTask;
    final hasRouteFab = hasActiveTask && driver.pilotsAwaitingPickup > 0;
    final navBottom = MediaQuery.of(context).padding.bottom;
    final connectionColor = driver.connected
        ? Colors.green
        : hasActiveTask
            ? Colors.red
            : Colors.grey;
    final connectionTooltip = driver.connected
        ? 'Connected'
        : hasActiveTask
            ? 'Disconnected'
            : 'Standalone tracking';
    final initialCenter = driverPosition != null
        ? LatLng(driverPosition.lat, driverPosition.lon)
        : pilots.isNotEmpty
            ? LatLng(pilots.first.lat, pilots.first.lon)
            : const LatLng(46.0, 11.0);

    _centerInitialMapIfNeeded();

    return Scaffold(
      appBar: AppBar(
        title: Text(driver.taskName ?? 'Driver Mode'),
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Settings',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
          IconButton(
            icon: Icon(driver.showAllPilots ? Icons.people : Icons.person),
            tooltip:
                driver.showAllPilots ? 'Show my pilots' : 'Show all pilots',
            onPressed: driver.toggleShowAllPilots,
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Tooltip(
              message: connectionTooltip,
              child: Icon(Icons.circle, size: 12, color: connectionColor),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: () {
              driver.disconnect();
              if (tracking.isTracking) {
                unawaited(tracking.stopTracking());
              }
              unawaited(auth.logout());
            },
          ),
          IconButton(
            icon: const Icon(Icons.power_settings_new),
            tooltip: 'Shut Down App',
            onPressed: () => confirmAppShutdown(context),
          ),
        ],
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _mapController,
            options: MapOptions(
              initialCenter: initialCenter,
              initialZoom: 12,
              onMapEvent: (event) {
                if (_isManualMapMove(event) &&
                    (!_userPanned || _followDriver)) {
                  setState(() {
                    _userPanned = true;
                    _followDriver = false;
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
                  if (driverPosition != null)
                    Marker(
                      point: LatLng(driverPosition.lat, driverPosition.lon),
                      width: 52,
                      height: 54,
                      child: const _DriverCarMarker(),
                    ),
                  ...pilots.map(
                    (pilot) => Marker(
                      point: LatLng(pilot.lat, pilot.lon),
                      width: 48,
                      height: 52,
                      child: GestureDetector(
                        onTap: () => _showPilotSheet(pilot),
                        child: _DriverPilotMarker(pilot: pilot),
                      ),
                    ),
                  ),
                ],
              ),
              AppMapScaleBar(
                padding: EdgeInsets.only(
                  left: 12,
                  bottom: (hasRouteFab ? 82 : 12) + navBottom,
                ),
              ),
            ],
          ),
          Positioned(
            top: 12,
            right: 12,
            child: LiveMapStyleDropdown(
              value: _mapStyle,
              onChanged: (style) => setState(() => _mapStyle = style),
            ),
          ),
          Positioned(
            bottom: 16 + navBottom,
            right: 16,
            child: FloatingActionButton.small(
              tooltip: _followDriver ? 'Following GPS' : 'Center on GPS',
              backgroundColor: _followDriver ? theme.colorScheme.primary : null,
              foregroundColor:
                  _followDriver ? theme.colorScheme.onPrimary : null,
              onPressed: _centerOnDriver,
              child: const Icon(Icons.my_location),
            ),
          ),
          if (hasRouteFab)
            Positioned(
              bottom: 16 + navBottom,
              left: 16,
              child: FloatingActionButton.extended(
                icon: const Icon(Icons.route),
                label: Text('Route (${driver.pilotsAwaitingPickup})'),
                onPressed: () {
                  final taskId = driver.taskId;
                  if (taskId == null) return;
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      builder: (_) => DriverNavigationScreen(taskId: taskId),
                    ),
                  );
                },
              ),
            ),
        ],
      ),
    );
  }
}

class _DriverCarMarker extends StatelessWidget {
  const _DriverCarMarker();

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(6),
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 2),
            boxShadow: [
              BoxShadow(color: Colors.black.withAlpha(45), blurRadius: 4),
            ],
          ),
          child: Icon(Icons.directions_car, size: 22, color: color),
        ),
        Text(
          'You',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.bold,
            color: color,
          ),
        ),
      ],
    );
  }
}

class _DriverPilotMarker extends StatelessWidget {
  final DriverPilot pilot;

  const _DriverPilotMarker({required this.pilot});

  Color get _statusColor {
    switch (pilot.status) {
      case 'ready':
        return Colors.green;
      case 'landed':
        return Colors.orange;
      case 'picked_up':
        return Colors.blue;
      default:
        return pilot.assigned ? Colors.blue : Colors.grey;
    }
  }

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
    final color = _statusColor;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 2),
            boxShadow: [
              BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 3),
            ],
          ),
          child: Icon(
            _iconForAircraft(pilot.aircraftIcon),
            size: 18,
            color: color,
          ),
        ),
        Container(
          constraints: const BoxConstraints(maxWidth: 62),
          padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
          decoration: BoxDecoration(
            color: Colors.white.withAlpha(215),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            pilot.compNumber != null ? '#${pilot.compNumber}' : pilot.name,
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

class _PilotMetric extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _PilotMetric({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 18, color: theme.colorScheme.primary),
        const SizedBox(width: 6),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
            Text(value, style: theme.textTheme.bodyMedium),
          ],
        ),
      ],
    );
  }
}

class _PilotStatusBadge extends StatelessWidget {
  final DriverPilot pilot;

  const _PilotStatusBadge({required this.pilot});

  @override
  Widget build(BuildContext context) {
    Color color;
    String label;

    switch (pilot.status) {
      case 'landed':
        color = Colors.orange;
        final mins = pilot.minutesUntilReady;
        label = mins > 0 ? 'Landed (${mins}m)' : 'Ready';
        break;
      case 'ready':
        color = Colors.green;
        label = 'Ready';
        break;
      case 'picked_up':
        color = Colors.blue;
        label = 'Picked up';
        break;
      default:
        color = Colors.grey;
        label = 'Flying';
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: color.withAlpha(30),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w600,
          color: color,
        ),
      ),
    );
  }
}
