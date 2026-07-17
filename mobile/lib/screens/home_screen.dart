import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/turnpoint.dart';
import '../models/meshtastic_protobufs.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/driver_service.dart';
import '../services/tracking_service.dart';
import '../utils/app_shutdown.dart';
import '../utils/unit_converter.dart';
import '../widgets/aervyx_logo.dart';
import '../widgets/live_tracking_map_helpers.dart';
import 'events_screen.dart';
import 'flights_screen.dart';
import 'live_view_screen.dart';
import 'meshtastic_settings_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _driverStartInProgress = false;
  bool _driverStartAttempted = false;
  bool _driverConnectAttempted = false;

  void _ensureDriverRelay(
    AuthService auth,
    TrackingService tracking,
    DriverService driver,
  ) {
    if (auth.user?.profileType != 'driver') {
      if (_driverConnectAttempted) {
        driver.disconnect();
      }
      _driverStartAttempted = false;
      _driverConnectAttempted = false;
      return;
    }
    if (!_driverConnectAttempted) {
      _driverConnectAttempted = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        driver.connect();
      });
    }
    if (tracking.isTracking ||
        _driverStartInProgress ||
        _driverStartAttempted) {
      return;
    }

    _driverStartInProgress = true;
    _driverStartAttempted = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      try {
        await tracking.startTracking();
      } finally {
        if (mounted) {
          setState(() => _driverStartInProgress = false);
        } else {
          _driverStartInProgress = false;
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final tracking = context.watch<TrackingService>();
    final ble = context.watch<BleService>();
    final driver = context.watch<DriverService>();
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDriverProfile = auth.user?.profileType == 'driver';
    _ensureDriverRelay(auth, tracking, driver);

    return Scaffold(
      appBar: AppBar(
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            CustomPaint(
              size: const Size(24, 24),
              painter: _AppBarLogoPainter(),
            ),
            const SizedBox(width: 8),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text(
                  'Aervyx',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 18,
                    color: AervyxLogo.cyan,
                  ),
                ),
                if (ble.isConnected)
                  Text(
                    ble.deviceDisplayName,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w400,
                      color: Colors.grey.shade600,
                    ),
                  ),
              ],
            ),
          ],
        ),
        actions: [
          // Connection status indicator
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Tooltip(
              message: tracking.isTracking
                  ? (tracking.backendConnected ? 'Connected' : 'Disconnected')
                  : 'Not tracking',
              child: Icon(
                Icons.circle,
                size: 12,
                color: !tracking.isTracking
                    ? Colors.grey
                    : tracking.backendConnected
                        ? Colors.green
                        : Colors.red,
              ),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.event_outlined),
            tooltip: 'Events',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => EventsScreen(
                  api: context.read<ApiService>(),
                  canManageEvents: auth.user?.role == 'admin' ||
                      auth.user?.role == 'organizer',
                ),
              ),
            ),
          ),
          if (!isDriverProfile)
            IconButton(
              icon: const Icon(Icons.flight),
              tooltip: 'Logbook',
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const FlightsScreen()),
              ),
            ),
          IconButton(
            icon: const Icon(Icons.map),
            tooltip: 'Live View',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const LiveViewScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            tooltip: 'Settings',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SettingsScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.power_settings_new),
            tooltip: 'Shut Down App',
            onPressed: () => confirmAppShutdown(context),
          ),
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              const SizedBox(height: 16),

              // Debug mode banner
              if (tracking.debugMode)
                Container(
                  width: double.infinity,
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  margin: const EdgeInsets.only(bottom: 8),
                  decoration: BoxDecoration(
                    color: Colors.orange.withAlpha(30),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.orange.withAlpha(80)),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Icon(Icons.bug_report,
                          size: 16, color: Colors.orange),
                      const SizedBox(width: 6),
                      Text(
                        'Debug Mode — all positions sent to server',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: Colors.orange,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),

              // Big tracking button — 3 states
              if (isDriverProfile)
                _DriverRelayStatusPanel(
                  tracking: tracking,
                  driver: driver,
                  starting: _driverStartInProgress,
                )
              else
                _TrackingButton(tracking: tracking),

              const SizedBox(height: 8),

              if (!isDriverProfile)
                _FlightTimeDisplay(
                  tracking: tracking,
                ),

              if (isDriverProfile) ...[
                const SizedBox(height: 8),
                _DriverPilotRelayCard(
                  pilots: driver.visiblePilots,
                  activeTask: tracking.activeTask,
                  altitudeUnit: auth.user?.altitudeUnit ?? 'm',
                  distanceUnit: auth.user?.distanceUnit ?? 'km',
                ),
              ],

              // Status text (pre-flight, monitoring, landing countdown)
              if (!isDriverProfile) _StatusText(tracking: tracking),

              const SizedBox(height: 8),

              // Landing countdown cancel button
              if (tracking.landingCountdownActive)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: FilledButton.icon(
                    onPressed: () => tracking.cancelLandingCountdown(),
                    icon: const Icon(Icons.cancel),
                    label: Text(
                      'Cancel — still flying (${tracking.landingCountdownRemaining}s)',
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.orange,
                    ),
                  ),
                ),

              if (!isDriverProfile) ...[
                _ActiveTaskLabel(tracking: tracking),
                if (tracking.activeTask != null) const SizedBox(height: 8),
              ],

              if (isDriverProfile)
                _DriverSosAlertsCard(alerts: driver.activeSosAlerts)
              else
                _SosButton(ble: ble),

              const SizedBox(height: 12),

              // ── Connection Status (compact LED rows) ──
              _StatusRow(
                icon: Icons.gps_fixed,
                label: 'GPS',
                statusText: isDriverProfile
                    ? (tracking.isDriverTracking
                        ? 'Relaying'
                        : _driverStartInProgress
                            ? 'Starting'
                            : 'Waiting')
                    : tracking.isTracking
                        ? _trackingStateLabel(tracking.trackingState)
                        : 'Off',
                ledColor: tracking.isTracking
                    ? Colors.green
                    : isDriverProfile && _driverStartInProgress
                        ? Colors.orange
                        : Colors.grey,
                expandedContent: _GpsDetails(tracking: tracking, auth: auth),
              ),
              const SizedBox(height: 4),
              _StatusRow(
                icon: Icons.cloud,
                label: 'Server',
                statusText:
                    tracking.backendConnected ? 'Connected' : 'Disconnected',
                ledColor: tracking.backendConnected ? Colors.green : Colors.red,
                expandedContent: _ServerDetails(tracking: tracking),
              ),
              const SizedBox(height: 4),
              _StatusRow(
                icon: Icons.bluetooth,
                label: 'Mesh Radio',
                labelTrailing: ble.isConnected && ble.deviceBatteryLevel != null
                    ? _MeshBatteryBadge(ble: ble)
                    : null,
                statusText: ble.isConnected && ble.deviceBatteryLevel != null
                    ? ''
                    : ble.isConnected
                        ? 'Paired'
                        : 'Not Paired',
                ledColor: ble.isConnected ? Colors.green : Colors.grey,
                expandedContent: _MeshDetails(ble: ble),
              ),

              const SizedBox(height: 12),

              // Notification message (success / warning / error)
              if (tracking.meshReconnectWarning != null)
                Card(
                  color: colorScheme.tertiaryContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Icon(Icons.bluetooth_disabled,
                            color: colorScheme.onTertiaryContainer, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            tracking.meshReconnectWarning!,
                            style: TextStyle(
                              color: colorScheme.onTertiaryContainer,
                              fontSize: 12,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),

              if (tracking.error != null &&
                  !tracking.error!.startsWith('Landing detected'))
                Builder(builder: (_) {
                  final Color bgColor;
                  final Color fgColor;
                  final IconData icon;
                  switch (tracking.notificationLevel) {
                    case NotificationLevel.success:
                      bgColor = colorScheme.primaryContainer;
                      fgColor = colorScheme.onPrimaryContainer;
                      icon = Icons.check_circle;
                      break;
                    case NotificationLevel.warning:
                      bgColor = colorScheme.tertiaryContainer;
                      fgColor = colorScheme.onTertiaryContainer;
                      icon = Icons.warning_amber_rounded;
                      break;
                    case NotificationLevel.error:
                      bgColor = colorScheme.errorContainer;
                      fgColor = colorScheme.onErrorContainer;
                      icon = Icons.error;
                      break;
                  }
                  return Card(
                    color: bgColor,
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          Icon(icon, color: fgColor, size: 18),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              tracking.error!,
                              style: TextStyle(color: fgColor, fontSize: 12),
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }),

              // Logout button at bottom
              TextButton.icon(
                onPressed: () {
                  if (tracking.isTracking) tracking.stopTracking();
                  driver.disconnect();
                  auth.logout();
                },
                icon: const Icon(Icons.logout),
                label: const Text('Log Out'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  static String _trackingStateLabel(TrackingState state) {
    switch (state) {
      case TrackingState.idle:
        return 'Off';
      case TrackingState.preFlight:
        return 'Pre-flight';
      case TrackingState.inFlight:
        return 'Recording';
      case TrackingState.monitoring:
        return 'Monitoring';
    }
  }
}

// ── 3-State Tracking Button ──

class _DriverRelayStatusPanel extends StatelessWidget {
  final TrackingService tracking;
  final DriverService driver;
  final bool starting;

  const _DriverRelayStatusPanel({
    required this.tracking,
    required this.driver,
    required this.starting,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final relaying = tracking.isDriverTracking;
    final connected = tracking.backendConnected;
    final Color accent = relaying
        ? connected
            ? Colors.green
            : Colors.orange
        : starting
            ? Colors.orange
            : colorScheme.onSurfaceVariant;
    final title = relaying
        ? 'Actively relaying'
        : starting
            ? 'Starting relay'
            : 'Relay waiting';
    final subtitle = relaying
        ? '${tracking.positionCount} points relayed'
        : 'Preparing driver GPS relay';
    final task = tracking.activeTask;
    final taskName = task?.taskName ?? driver.taskName;
    final goalName = task == null || task.turnpoints.isEmpty
        ? null
        : task.turnpoints.last.name;
    final taskDetail = task == null
        ? 'No active task'
        : [
            '${task.turnpoints.length} points',
            if (goalName != null && goalName.isNotEmpty) 'Goal: $goalName',
          ].join(' · ');

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withAlpha(160),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: accent.withAlpha(120)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                relaying ? Icons.directions_car : Icons.sync,
                size: 34,
                color: accent,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                        color: colorScheme.onSurface,
                      ),
                    ),
                    Text(
                      subtitle,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 10),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: accent.withAlpha(28),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: accent.withAlpha(90)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.timer, size: 16, color: accent),
                    const SizedBox(width: 5),
                    Text(
                      _formatRelayDuration(tracking.flightDuration),
                      style: theme.textTheme.labelLarge?.copyWith(
                        color: colorScheme.onSurface,
                        fontWeight: FontWeight.w700,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
            decoration: BoxDecoration(
              color: colorScheme.surface.withAlpha(120),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: colorScheme.outlineVariant),
            ),
            child: Row(
              children: [
                Icon(Icons.route, size: 18, color: colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        taskName == null || taskName.isEmpty
                            ? 'Current task'
                            : taskName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.labelLarge?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        taskDetail,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DriverPilotRelayCard extends StatelessWidget {
  final List<DriverPilot> pilots;
  final ActiveTask? activeTask;
  final String altitudeUnit;
  final String distanceUnit;

  const _DriverPilotRelayCard({
    required this.pilots,
    required this.activeTask,
    required this.altitudeUnit,
    required this.distanceUnit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Card(
      margin: EdgeInsets.zero,
      color: colorScheme.surfaceContainerHighest.withAlpha(120),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: colorScheme.outlineVariant.withAlpha(160)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.people_alt, size: 20, color: colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Pilot relay list',
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                Text(
                  '${pilots.length}',
                  style: theme.textTheme.labelLarge?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            _DriverPilotRelayTable(
              pilots: pilots,
              activeTask: activeTask,
              altitudeUnit: altitudeUnit,
              distanceUnit: distanceUnit,
            ),
          ],
        ),
      ),
    );
  }
}

class _DriverPilotRelayTable extends StatelessWidget {
  final List<DriverPilot> pilots;
  final ActiveTask? activeTask;
  final String altitudeUnit;
  final String distanceUnit;

  const _DriverPilotRelayTable({
    required this.pilots,
    required this.activeTask,
    required this.altitudeUnit,
    required this.distanceUnit,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final borderColor = theme.colorScheme.outlineVariant.withAlpha(180);
    return Container(
      height: 260,
      width: double.infinity,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor),
      ),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
            decoration: BoxDecoration(
              color: theme.colorScheme.surface.withAlpha(120),
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(8)),
            ),
            child: const Row(
              children: [
                Expanded(flex: 4, child: _DriverTableHeader('Name')),
                Expanded(flex: 3, child: _DriverTableHeader('Last')),
                Expanded(flex: 3, child: _DriverTableHeader('Alt')),
                Expanded(flex: 3, child: _DriverTableHeader('Goal')),
                Expanded(flex: 3, child: _DriverTableHeader('Status')),
                SizedBox(width: 36, child: _DriverTableHeader('Go')),
              ],
            ),
          ),
          Expanded(
            child: pilots.isEmpty
                ? Center(
                    child: Text(
                      'No pilots relayed yet',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  )
                : Scrollbar(
                    child: ListView.separated(
                      padding: EdgeInsets.zero,
                      itemCount: pilots.length,
                      separatorBuilder: (_, __) => Divider(
                        height: 1,
                        color: borderColor,
                      ),
                      itemBuilder: (context, index) {
                        final pilot = pilots[index];
                        return Padding(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 6,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                flex: 4,
                                child: Text(
                                  pilot.name,
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              Expanded(
                                flex: 3,
                                child: Text(
                                  _relativeRelayTime(pilot.lastSeen),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall,
                                ),
                              ),
                              Expanded(
                                flex: 3,
                                child: Text(
                                  UnitConverter.formatAltitude(
                                    pilot.alt,
                                    altitudeUnit,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall,
                                ),
                              ),
                              Expanded(
                                flex: 3,
                                child: Text(
                                  UnitConverter.formatDistance(
                                    _taskDistanceToGoalMeters(
                                      activeTask,
                                      pilot.lat,
                                      pilot.lon,
                                    ),
                                    distanceUnit,
                                  ),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall,
                                ),
                              ),
                              Expanded(
                                flex: 3,
                                child: Text(
                                  _driverPilotStatusLabel(pilot),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: theme.textTheme.bodySmall?.copyWith(
                                    color: _driverPilotStatusColor(pilot),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ),
                              SizedBox(
                                width: 36,
                                child: IconButton(
                                  tooltip: 'Directions to ${pilot.name}',
                                  icon: const Icon(Icons.directions, size: 18),
                                  visualDensity: VisualDensity.compact,
                                  padding: EdgeInsets.zero,
                                  constraints: const BoxConstraints.tightFor(
                                    width: 32,
                                    height: 32,
                                  ),
                                  onPressed: () =>
                                      _openDriverDirections(context, pilot),
                                ),
                              ),
                            ],
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}

class _DriverTableHeader extends StatelessWidget {
  final String text;

  const _DriverTableHeader(this.text);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Text(
      text,
      style: theme.textTheme.labelSmall?.copyWith(
        color: theme.colorScheme.onSurfaceVariant,
        fontWeight: FontWeight.w700,
      ),
    );
  }
}

Future<void> _openDriverDirections(
  BuildContext context,
  DriverPilot pilot,
) async {
  final geoUri = liveDirectionsGeoUri(pilot.lat, pilot.lon, label: pilot.name);
  if (await canLaunchUrl(geoUri)) {
    await launchUrl(geoUri);
    return;
  }
  final webUri = liveDirectionsWebUri(pilot.lat, pilot.lon);
  if (await canLaunchUrl(webUri)) {
    await launchUrl(webUri, mode: LaunchMode.externalApplication);
    return;
  }
  if (context.mounted) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('No navigation app found')),
    );
  }
}

double? _taskDistanceToGoalMeters(
  ActiveTask? task,
  double lat,
  double lon,
) {
  final points = task?.turnpoints;
  if (points == null || points.isEmpty) return null;
  if (points.length == 1) return points.first.distanceTo(lat, lon);

  final remainingAfterSegment = List<double>.filled(points.length - 1, 0);
  var tailDistance = 0.0;
  for (var i = points.length - 2; i >= 0; i--) {
    remainingAfterSegment[i] = tailDistance;
    tailDistance += points[i].distanceTo(points[i + 1].lat, points[i + 1].lon);
  }

  double? bestCrossTrack;
  double? bestRemaining;
  for (var i = 0; i < points.length - 1; i++) {
    final start = points[i];
    final end = points[i + 1];
    final projection = _projectPointOnSegment(
      lat,
      lon,
      start.lat,
      start.lon,
      end.lat,
      end.lon,
    );
    final remaining = projection.distanceToEndMeters + remainingAfterSegment[i];
    if (bestCrossTrack == null ||
        projection.crossTrackMeters < bestCrossTrack) {
      bestCrossTrack = projection.crossTrackMeters;
      bestRemaining = remaining;
    }
  }
  return bestRemaining;
}

_SegmentProjection _projectPointOnSegment(
  double lat,
  double lon,
  double startLat,
  double startLon,
  double endLat,
  double endLon,
) {
  const earthRadius = 6371000.0;
  final originLatRad = _degToRad(lat);
  const px = 0.0;
  const py = 0.0;
  final ax = _lonMeters(startLon - lon, originLatRad, earthRadius);
  final ay = _latMeters(startLat - lat, earthRadius);
  final bx = _lonMeters(endLon - lon, originLatRad, earthRadius);
  final by = _latMeters(endLat - lat, earthRadius);
  final abx = bx - ax;
  final aby = by - ay;
  final abLen2 = abx * abx + aby * aby;
  final rawT = abLen2 == 0 ? 0.0 : ((px - ax) * abx + (py - ay) * aby) / abLen2;
  final t = rawT.clamp(0.0, 1.0);
  final qx = ax + abx * t;
  final qy = ay + aby * t;
  return _SegmentProjection(
    crossTrackMeters: math.sqrt(qx * qx + qy * qy),
    distanceToEndMeters:
        math.sqrt((bx - qx) * (bx - qx) + (by - qy) * (by - qy)),
  );
}

double _latMeters(double degrees, double earthRadius) =>
    _degToRad(degrees) * earthRadius;

double _lonMeters(double degrees, double originLatRad, double earthRadius) =>
    _degToRad(degrees) * earthRadius * math.cos(originLatRad);

double _degToRad(double degrees) => degrees * math.pi / 180;

class _SegmentProjection {
  final double crossTrackMeters;
  final double distanceToEndMeters;

  const _SegmentProjection({
    required this.crossTrackMeters,
    required this.distanceToEndMeters,
  });
}

String _relativeRelayTime(DateTime? lastSeen) {
  if (lastSeen == null) return '--';
  final now = DateTime.now().toUtc();
  final elapsed = now.difference(lastSeen.toUtc());
  if (elapsed.inSeconds < 60) return '${elapsed.inSeconds.clamp(0, 59)}s ago';
  if (elapsed.inMinutes < 60) return '${elapsed.inMinutes}m ago';
  if (elapsed.inHours < 24) return '${elapsed.inHours}h ago';
  return '${elapsed.inDays}d ago';
}

String _driverPilotStatusLabel(DriverPilot pilot) {
  switch (pilot.status) {
    case 'landed':
      final mins = pilot.minutesUntilReady;
      return mins > 0 ? 'Landed ${mins}m' : 'Ready';
    case 'ready':
      return 'Ready';
    case 'picked_up':
      return 'Picked up';
    default:
      return 'Flying';
  }
}

Color _driverPilotStatusColor(DriverPilot pilot) {
  switch (pilot.status) {
    case 'landed':
      return Colors.orange;
    case 'ready':
      return Colors.green;
    case 'picked_up':
      return Colors.blue;
    default:
      return Colors.grey;
  }
}

class _TrackingButton extends StatelessWidget {
  final TrackingService tracking;

  const _TrackingButton({required this.tracking});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    // Determine button appearance based on state
    Color bgColor;
    Color fgColor;
    IconData icon;
    String label;

    switch (tracking.trackingState) {
      case TrackingState.idle:
        bgColor = colorScheme.primary;
        fgColor = colorScheme.onPrimary;
        icon = Icons.play_arrow_rounded;
        label = 'Start';
        break;
      case TrackingState.preFlight:
        bgColor = Colors.teal;
        fgColor = Colors.white;
        icon = Icons.flight_takeoff;
        label = 'Waiting...';
        break;
      case TrackingState.inFlight:
        if (tracking.landingDetected) {
          bgColor = Colors.orange;
          fgColor = Colors.white;
          icon = Icons.flight_land;
          label = 'Landing...';
        } else {
          bgColor = colorScheme.error;
          fgColor = colorScheme.onError;
          icon = Icons.stop_rounded;
          label = 'Stop';
        }
        break;
      case TrackingState.monitoring:
        bgColor = Colors.amber.shade700;
        fgColor = Colors.white;
        icon = Icons.pause_rounded;
        label = 'Monitoring';
        break;
    }

    return SizedBox(
      width: 180,
      height: 180,
      child: GestureDetector(
        onLongPress: tracking.trackingState == TrackingState.preFlight
            ? () => tracking.forceStartRecording()
            : null,
        child: FilledButton(
          onPressed: () {
            switch (tracking.trackingState) {
              case TrackingState.idle:
                tracking.startTracking();
                break;
              case TrackingState.preFlight:
                // Short press during pre-flight → stop
                tracking.stopTracking();
                break;
              case TrackingState.inFlight:
                tracking.stopTracking();
                break;
              case TrackingState.monitoring:
                tracking.stopTracking();
                break;
            }
          },
          style: FilledButton.styleFrom(
            shape: const CircleBorder(),
            backgroundColor: bgColor,
            foregroundColor: fgColor,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(icon, size: 56),
              const SizedBox(height: 4),
              Text(
                label,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

// ── Status Text ──

class _StatusText extends StatelessWidget {
  final TrackingService tracking;

  const _StatusText({required this.tracking});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String? text;
    Color? color;

    switch (tracking.trackingState) {
      case TrackingState.preFlight:
        text = 'Waiting for takeoff...\nLong-press to force start';
        color = theme.colorScheme.primary;
        break;
      case TrackingState.monitoring:
        text = 'Monitoring for re-launch...';
        color = Colors.amber.shade700;
        break;
      case TrackingState.inFlight:
        if (tracking.landingCountdownActive) {
          text =
              'Landing detected — stopping in ${tracking.landingCountdownRemaining}s';
          color = Colors.orange;
        } else if (tracking.landingDetected) {
          text = 'Landing detected — confirming...';
          color = Colors.orange;
        }
        break;
      case TrackingState.idle:
        break;
    }

    if (text == null) return const SizedBox.shrink();

    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 4),
      child: Text(
        text,
        textAlign: TextAlign.center,
        style: theme.textTheme.bodySmall?.copyWith(
          color: color,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }
}

// ── Compact Status Row with LED Indicator ──

class _StatusRow extends StatefulWidget {
  final IconData icon;
  final String label;
  final Widget? labelTrailing;
  final String statusText;
  final Color ledColor;
  final Widget expandedContent;

  const _StatusRow({
    required this.icon,
    required this.label,
    this.labelTrailing,
    required this.statusText,
    required this.ledColor,
    required this.expandedContent,
  });

  @override
  State<_StatusRow> createState() => _StatusRowState();
}

class _StatusRowState extends State<_StatusRow> {
  bool _expanded = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final hasGlow = widget.ledColor != Colors.grey;

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
              child: Row(
                children: [
                  Icon(widget.icon, size: 20, color: theme.colorScheme.primary),
                  const SizedBox(width: 12),
                  Text(
                    widget.label,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (widget.labelTrailing != null) ...[
                    const SizedBox(width: 6),
                    widget.labelTrailing!,
                  ],
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      widget.statusText,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                  const SizedBox(width: 8),
                  // LED dot with glow
                  Container(
                    width: 12,
                    height: 12,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: widget.ledColor,
                      boxShadow: hasGlow
                          ? [
                              BoxShadow(
                                color: widget.ledColor.withAlpha(128),
                                blurRadius: 6,
                                spreadRadius: 1,
                              ),
                            ]
                          : null,
                    ),
                  ),
                ],
              ),
            ),
          ),
          ClipRect(
            child: AnimatedSize(
              duration: const Duration(milliseconds: 200),
              curve: Curves.easeInOut,
              alignment: Alignment.topCenter,
              child: _expanded
                  ? Padding(
                      padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
                      child: widget.expandedContent,
                    )
                  : const SizedBox(width: double.infinity, height: 0),
            ),
          ),
        ],
      ),
    );
  }
}

// ── GPS Details (expanded content) ──

class _ActiveTaskLabel extends StatelessWidget {
  final TrackingService tracking;

  const _ActiveTaskLabel({required this.tracking});

  @override
  Widget build(BuildContext context) {
    final task = tracking.activeTask;
    if (!tracking.isTracking || task == null) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: colorScheme.primaryContainer.withAlpha(150),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: colorScheme.primary.withAlpha(90)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.flag, size: 16, color: colorScheme.primary),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              'Task: ${task.taskName}',
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.labelMedium?.copyWith(
                color: colorScheme.onPrimaryContainer,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _GpsDetails extends StatelessWidget {
  final TrackingService tracking;
  final AuthService auth;

  const _GpsDetails({required this.tracking, required this.auth});

  String _zoneLabel(TrackingZone zone) {
    switch (zone) {
      case TrackingZone.stationary:
        return 'Every 5s';
      case TrackingZone.normalFlight:
        return 'Every 1s';
      case TrackingZone.approaching:
        return 'Every 0.2s';
      case TrackingZone.critical:
        return 'Every 0.1s';
    }
  }

  String _nearestTpLabel(double? dist) {
    if (dist == null) return '--';
    if (dist < 1000) return '${dist.toStringAsFixed(0)} m';
    return '${(dist / 1000).toStringAsFixed(1)} km';
  }

  @override
  Widget build(BuildContext context) {
    final pos = tracking.lastPosition;
    final user = auth.user;
    final altUnit = user?.altitudeUnit ?? 'ft';
    final speedUnit = user?.speedUnit ?? 'kph';

    return Table(
      columnWidths: const {
        0: FlexColumnWidth(1),
        1: FlexColumnWidth(1),
      },
      children: [
        _buildRow(
          Icons.height,
          'Altitude',
          UnitConverter.formatAltitude(pos?.alt, altUnit),
          Icons.speed,
          'Speed',
          UnitConverter.formatSpeed(pos?.speed, speedUnit),
          context,
        ),
        _buildRow(
          Icons.explore,
          'Heading',
          pos?.heading != null
              ? '${pos!.heading!.toStringAsFixed(0)}\u00B0'
              : '--',
          Icons.gps_fixed,
          'Accuracy',
          pos?.accuracy != null
              ? '${pos!.accuracy!.toStringAsFixed(1)} m'
              : '--',
          context,
        ),
        _buildRow(
          Icons.tune,
          'GPS Rate',
          tracking.isInFlight ? _zoneLabel(tracking.currentZone) : '--',
          Icons.flag,
          'Nearest TP',
          tracking.inCompetitionMode
              ? _nearestTpLabel(tracking.nearestTurnpointDistance)
              : 'Free flight',
          context,
        ),
      ],
    );
  }

  TableRow _buildRow(
    IconData icon1,
    String label1,
    String value1,
    IconData icon2,
    String label2,
    String value2,
    BuildContext context,
  ) {
    return TableRow(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: _StatTile(icon: icon1, label: label1, value: value1),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: _StatTile(icon: icon2, label: label2, value: value2),
        ),
      ],
    );
  }
}

// ── Server Details (expanded content) ──

class _ServerDetails extends StatelessWidget {
  final TrackingService tracking;

  const _ServerDetails({required this.tracking});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (!tracking.isTracking) {
      return Row(
        children: [
          Icon(Icons.cloud_off,
              color: theme.colorScheme.onSurfaceVariant, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              'Start tracking to connect to the Aervyx server.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ),
        ],
      );
    }

    final buffered = tracking.bufferedPositionCount;

    return Table(
      columnWidths: const {
        0: FlexColumnWidth(1),
        1: FlexColumnWidth(1),
      },
      children: [
        TableRow(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: _StatTile(
                icon: tracking.backendConnected
                    ? Icons.cloud_done
                    : Icons.cloud_off,
                label: 'Status',
                value: tracking.backendConnected ? 'Connected' : 'Disconnected',
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: _StatTile(
                icon: Icons.cloud_upload,
                label: 'Points Sent',
                value: '${tracking.positionCount}',
              ),
            ),
          ],
        ),
        TableRow(
          children: [
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: _StatTile(
                icon: Icons.schedule,
                label: 'Buffered',
                value: buffered > 0 ? '$buffered pending' : 'None',
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 6),
              child: _StatTile(
                icon: tracking.inCompetitionMode
                    ? Icons.emoji_events
                    : tracking.driverMode
                        ? Icons.directions_car
                        : Icons.paragliding,
                label: 'Mode',
                value: tracking.inCompetitionMode
                    ? 'Competition'
                    : tracking.driverMode
                        ? 'Driver Relay'
                        : 'Free Flight',
              ),
            ),
          ],
        ),
      ],
    );
  }
}

// ── Mesh Details (expanded content) ──

class _MeshBatteryBadge extends StatelessWidget {
  final BleService ble;

  const _MeshBatteryBadge({required this.ble});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final level = ble.deviceBatteryLevel;
    if (level == null) return const SizedBox.shrink();

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: _batteryIconColor(level).withAlpha(24),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: _batteryIconColor(level).withAlpha(96)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(_batteryIcon(level), size: 13, color: _batteryIconColor(level)),
          const SizedBox(width: 3),
          Text(
            level == 101 ? 'USB' : '$level%',
            style: theme.textTheme.labelSmall?.copyWith(
              color: _batteryIconColor(level),
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _MeshDetails extends StatelessWidget {
  final BleService ble;

  const _MeshDetails({required this.ble});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (!ble.isConnected) {
      return InkWell(
        onTap: () => Navigator.of(context).push(
          MaterialPageRoute(builder: (_) => const MeshtasticSettingsScreen()),
        ),
        borderRadius: BorderRadius.circular(8),
        child: Row(
          children: [
            Icon(Icons.bluetooth_disabled,
                color: theme.colorScheme.onSurfaceVariant, size: 20),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                'No Meshtastic device paired.\nTap to connect.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.primary,
                ),
              ),
            ),
            Icon(Icons.arrow_forward_ios,
                size: 14, color: theme.colorScheme.primary),
          ],
        ),
      );
    }

    final ds = ble.deviceState;
    final auth = context.read<AuthService>();
    final altUnit = auth.user?.altitudeUnit ?? 'ft';

    // Map Meshtastic device role to Aervyx profile name
    String profileName;
    IconData profileIcon;
    switch (ds.role) {
      case DeviceRole.tracker:
        profileName = 'Pilot';
        profileIcon = Icons.flight;
        break;
      case DeviceRole.router:
        profileName = 'Repeater';
        profileIcon = Icons.cell_tower;
        break;
      case DeviceRole.client:
        profileName = ds.wifiEnabled ? 'Driver Wi-Fi' : 'Driver';
        profileIcon = ds.wifiEnabled ? Icons.wifi : Icons.directions_car;
        break;
      default:
        profileName = ds.role.label;
        profileIcon = Icons.devices;
    }

    return Column(
      children: [
        // Device name row
        Row(
          children: [
            Icon(Icons.bluetooth_connected,
                size: 16, color: theme.colorScheme.primary),
            const SizedBox(width: 6),
            Text(
              ble.deviceDisplayName,
              style: theme.textTheme.labelMedium?.copyWith(
                fontWeight: FontWeight.w600,
              ),
            ),
            if (ds.firmwareVersion != null) ...[
              const SizedBox(width: 8),
              Text(
                'v${ds.firmwareVersion}',
                style: theme.textTheme.labelSmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                ),
              ),
            ],
            const Spacer(),
            SizedBox(
              width: 28,
              height: 28,
              child: IconButton(
                iconSize: 18,
                padding: EdgeInsets.zero,
                icon: Icon(Icons.settings,
                    color: theme.colorScheme.onSurfaceVariant),
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute(
                      builder: (_) => const MeshtasticSettingsScreen()),
                ),
              ),
            ),
          ],
        ),
        const Divider(height: 12),
        // Mesh stats grid — compact 2×2: Profile, GPS, Altitude, Battery
        Table(
          columnWidths: const {
            0: FlexColumnWidth(1),
            1: FlexColumnWidth(1),
          },
          children: [
            TableRow(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: _StatTile(
                    icon: profileIcon,
                    label: 'Profile',
                    value: profileName,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: _StatTile(
                    icon: ds.gpsMode == GpsMode.notPresent
                        ? Icons.gps_off
                        : Icons.satellite_alt,
                    label: 'GPS',
                    value: _formatDeviceGps(ble, ds),
                    iconColor: _gpsIconColor(ble, ds),
                  ),
                ),
              ],
            ),
            TableRow(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: _StatTile(
                    icon: Icons.terrain,
                    label: 'Altitude',
                    value: _formatDeviceAltitude(ble, ds, altUnit),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: _StatTile(
                    icon: _batteryIcon(ble.deviceBatteryLevel),
                    label: 'Battery',
                    value: _formatBattery(ble),
                    iconColor: _batteryIconColor(ble.deviceBatteryLevel),
                  ),
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}

// ── Flight Time Display ──

class _FlightTimeDisplay extends StatelessWidget {
  final TrackingService tracking;

  const _FlightTimeDisplay({required this.tracking});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final duration = tracking.flightDuration;
    final isActive = tracking.isInFlight;

    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.timer,
          size: 18,
          color: isActive
              ? theme.colorScheme.primary
              : theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 6),
        Text(
          _formatRelayDuration(duration),
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w600,
            fontFeatures: const [FontFeature.tabularFigures()],
            color: isActive
                ? theme.colorScheme.onSurface
                : theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}

String _formatRelayDuration(Duration d) {
  final hours = d.inHours.toString().padLeft(2, '0');
  final minutes = (d.inMinutes % 60).toString().padLeft(2, '0');
  final seconds = (d.inSeconds % 60).toString().padLeft(2, '0');
  return '$hours:$minutes:$seconds';
}

// ── SOS Button ──

class _DriverSosAlertsCard extends StatelessWidget {
  final List<DriverSosAlert> alerts;

  const _DriverSosAlertsCard({required this.alerts});

  @override
  Widget build(BuildContext context) {
    if (alerts.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final latest = alerts.first;
    final count = alerts.length;
    final message = latest.message == null || latest.message!.trim().isEmpty
        ? 'Pilot needs immediate assistance'
        : latest.message!.trim();

    return Card(
      color: theme.colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.sos, color: theme.colorScheme.onErrorContainer),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    count == 1
                        ? 'SOS from ${latest.displayPilotName}'
                        : '$count active SOS alerts',
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    message,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _SosButton extends StatelessWidget {
  final BleService ble;

  const _SosButton({required this.ble});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 44,
      child: OutlinedButton(
        onPressed: ble.isSendingSos ? null : () => _confirmSos(context),
        style: OutlinedButton.styleFrom(
          side: const BorderSide(color: Colors.red, width: 1.5),
        ),
        child: ble.isSendingSos
            ? const Text('Sending...',
                style: TextStyle(fontWeight: FontWeight.bold))
            : Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: 'Send ',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                    const TextSpan(
                      text: 'SOS',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: Colors.red,
                      ),
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  void _confirmSos(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text.rich(
          TextSpan(
            children: [
              TextSpan(text: 'Send '),
              TextSpan(
                text: 'SOS',
                style: TextStyle(color: Colors.red),
              ),
              TextSpan(text: '?'),
            ],
          ),
        ),
        content: Text(
          'This will broadcast your SOS on all available channels '
          '(mesh network + cellular):\n\n"${ble.sosMessage}"',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.of(ctx).pop();
              ble.sendSos();
            },
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Send SOS'),
          ),
        ],
      ),
    );
  }
}

// ── Stat Tile (shared) ──

/// Format the GPS tile value: "No GPS", "Disabled", satellite count, or searching.
String _formatDeviceGps(BleService ble, MeshtasticDeviceState ds) {
  if (ds.gpsMode == GpsMode.notPresent) return 'Not present';
  if (ds.gpsMode == GpsMode.disabled) return 'Disabled';
  if (!ble.deviceHasGpsFix) return 'Searching…';
  // Has a fix — show satellite count + quality when available
  final parts = <String>[];
  final sats = ble.deviceGpsSats;
  if (sats != null && sats > 0) {
    parts.add('$sats sats');
  }
  final pdop = ble.deviceGpsPdop;
  if (pdop != null) {
    final quality = pdop < 2.0
        ? 'excellent'
        : pdop < 5.0
            ? 'good'
            : pdop < 10.0
                ? 'fair'
                : 'poor';
    parts.add(quality);
  }
  if (parts.isEmpty) return '3D Fix';
  return parts.join(' · ');
}

/// Format the device altitude from its GPS using the user's preferred unit.
String _formatDeviceAltitude(
    BleService ble, MeshtasticDeviceState ds, String altUnit) {
  if (ds.gpsMode == GpsMode.notPresent) return 'N/A';
  if (!ble.deviceHasGpsFix) return '--';
  return UnitConverter.formatAltitude(ble.deviceGpsAlt, altUnit);
}

/// Format battery display: percentage, "Powered" (USB), or "--" if unknown.
String _formatBattery(BleService ble) {
  final level = ble.deviceBatteryLevel;
  if (level == null) return '--';
  if (level == 101) return 'USB powered';
  final voltage = ble.deviceVoltage;
  if (voltage != null) {
    return '$level% · ${voltage.toStringAsFixed(1)}V';
  }
  return '$level%';
}

/// Pick battery icon based on level.
IconData _batteryIcon(int? level) {
  if (level == null) return Icons.battery_unknown;
  if (level == 101) return Icons.power;
  if (level > 90) return Icons.battery_full;
  if (level > 60) return Icons.battery_5_bar;
  if (level > 40) return Icons.battery_3_bar;
  if (level > 20) return Icons.battery_2_bar;
  return Icons.battery_alert;
}

/// GPS icon color based on device state.
Color _gpsIconColor(BleService ble, MeshtasticDeviceState ds) {
  if (ds.gpsMode == GpsMode.notPresent) return Colors.grey;
  if (ds.gpsMode == GpsMode.disabled) return Colors.orange;
  if (!ble.deviceHasGpsFix) return Colors.orange;
  return Colors.green;
}

/// Battery icon color based on level.
Color _batteryIconColor(int? level) {
  if (level == null) return Colors.grey;
  if (level == 101) return Colors.green;
  if (level > 60) return Colors.green;
  if (level >= 20) return Colors.orange;
  return Colors.red;
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color? iconColor;

  const _StatTile({
    required this.icon,
    required this.label,
    required this.value,
    this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: iconColor ?? theme.colorScheme.primary),
        const SizedBox(width: 6),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              value,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            Text(
              label,
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

/// Small Aervyx triangle logo for the AppBar.
class _AppBarLogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    final path = Path()
      ..moveTo(w * 0.5, h * 0.08)
      ..lineTo(w * 0.92, h * 0.88)
      ..lineTo(w * 0.5, h * 0.66)
      ..lineTo(w * 0.08, h * 0.88)
      ..close();

    final strokePaint = Paint()
      ..color = AervyxLogo.cyan
      ..style = PaintingStyle.stroke
      ..strokeWidth = w * 0.06
      ..strokeJoin = StrokeJoin.round;

    canvas.drawPath(path, strokePaint);

    final dotPaint = Paint()
      ..color = AervyxLogo.cyan.withAlpha(220)
      ..style = PaintingStyle.fill;

    canvas.drawCircle(Offset(w * 0.5, h * 0.44), w * 0.08, dotPaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
