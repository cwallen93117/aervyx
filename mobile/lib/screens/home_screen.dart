import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/meshtastic_protobufs.dart';
import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/tracking_service.dart';
import '../utils/app_shutdown.dart';
import '../utils/unit_converter.dart';
import '../widgets/aervyx_logo.dart';
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

  void _ensureDriverRelay(AuthService auth, TrackingService tracking) {
    if (auth.user?.profileType != 'driver' ||
        tracking.isTracking ||
        _driverStartInProgress) {
      return;
    }

    _driverStartInProgress = true;
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
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final isDriverProfile = auth.user?.profileType == 'driver';
    _ensureDriverRelay(auth, tracking);

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
                Text(
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
            icon: const Icon(Icons.map),
            tooltip: 'Live View',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const LiveViewScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.flight),
            tooltip: 'Flights',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const FlightsScreen()),
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
                  ble: ble,
                  starting: _driverStartInProgress,
                )
              else
                _TrackingButton(tracking: tracking),

              const SizedBox(height: 8),

              // Flight time — right below the button
              _FlightTimeDisplay(
                tracking: tracking,
                label: isDriverProfile ? 'Relay time' : null,
              ),

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

              _ActiveTaskLabel(tracking: tracking),

              if (tracking.activeTask != null) const SizedBox(height: 8),

              // SOS button
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
  final BleService ble;
  final bool starting;

  const _DriverRelayStatusPanel({
    required this.tracking,
    required this.ble,
    required this.starting,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final relaying = tracking.isDriverTracking;
    final connected = tracking.backendConnected;
    final buffered = tracking.bufferedPositionCount;
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

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest.withAlpha(160),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: accent.withAlpha(120)),
      ),
      child: Column(
        children: [
          Icon(
            relaying ? Icons.directions_car : Icons.sync,
            size: 44,
            color: accent,
          ),
          const SizedBox(height: 8),
          Text(
            title,
            textAlign: TextAlign.center,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
              color: colorScheme.onSurface,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: _RelayMiniStatus(
                  icon: connected ? Icons.cloud_done : Icons.cloud_off,
                  label: 'Server',
                  value: connected
                      ? 'Online'
                      : buffered > 0
                          ? '$buffered queued'
                          : 'Offline',
                  color: connected ? Colors.green : Colors.red,
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: _RelayMiniStatus(
                  icon: ble.isConnected
                      ? Icons.bluetooth_connected
                      : Icons.bluetooth_disabled,
                  label: 'Mesh',
                  value: ble.isConnected ? ble.deviceDisplayName : 'Not paired',
                  color: ble.isConnected ? Colors.green : Colors.grey,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _RelayMiniStatus extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _RelayMiniStatus({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      constraints: const BoxConstraints(minHeight: 58),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withAlpha(80)),
      ),
      child: Row(
        children: [
          Icon(icon, size: 20, color: color),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Text(
                  label,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
                Text(
                  value,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelMedium?.copyWith(
                    fontWeight: FontWeight.w700,
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
  final String? label;

  const _FlightTimeDisplay({required this.tracking, this.label});

  String _formatDuration(Duration d) {
    final hours = d.inHours.toString().padLeft(2, '0');
    final minutes = (d.inMinutes % 60).toString().padLeft(2, '0');
    final seconds = (d.inSeconds % 60).toString().padLeft(2, '0');
    return '$hours:$minutes:$seconds';
  }

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
        if (label != null) ...[
          Text(
            label!,
            style: theme.textTheme.labelMedium?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(width: 6),
        ],
        Text(
          _formatDuration(duration),
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

// ── SOS Button ──

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
        title: Text.rich(
          TextSpan(
            children: [
              const TextSpan(text: 'Send '),
              const TextSpan(
                text: 'SOS',
                style: TextStyle(color: Colors.red),
              ),
              const TextSpan(text: '?'),
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
