import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/meshtastic_protobufs.dart';
import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/tracking_service.dart';
import '../utils/unit_converter.dart';
import '../widgets/aervyx_logo.dart';
import 'flights_screen.dart';
import 'live_view_screen.dart';
import 'settings_screen.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final tracking = context.watch<TrackingService>();
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

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
        ],
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(
            children: [
              const SizedBox(height: 16),

              // Big tracking button — 3 states
              _TrackingButton(tracking: tracking),

              const SizedBox(height: 8),

              // Flight time — right below the button
              _FlightTimeDisplay(tracking: tracking),

              // Status text (pre-flight, monitoring, landing countdown)
              _StatusText(tracking: tracking),

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

              // SOS button
              _SosButton(ble: ble),

              const SizedBox(height: 12),

              // ── Stats ──
              // GPS stats card
              _SectionHeader(
                icon: Icons.gps_fixed,
                label: 'GPS',
                statusColor: tracking.isTracking ? Colors.green : Colors.grey,
                statusLabel: tracking.isTracking
                    ? _trackingStateLabel(tracking.trackingState)
                    : 'Off',
              ),
              _GpsStatsCard(tracking: tracking, auth: auth),

              const SizedBox(height: 12),

              // Mesh / BLE stats card
              _SectionHeader(
                icon: Icons.bluetooth,
                label: 'Mesh Radio',
                statusColor: ble.isConnected ? Colors.green : Colors.grey,
                statusLabel: ble.isConnected ? 'Connected' : 'Not Paired',
              ),
              _MeshStatsCard(ble: ble),

              const SizedBox(height: 12),

              // Error message
              if (tracking.error != null &&
                  !tracking.error!.startsWith('Landing detected'))
                Card(
                  color: colorScheme.errorContainer,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        Icon(Icons.warning_amber_rounded,
                            color: colorScheme.onErrorContainer, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            tracking.error!,
                            style: TextStyle(
                              color: colorScheme.onErrorContainer,
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
        bgColor = colorScheme.primary;
        fgColor = colorScheme.onPrimary;
        icon = Icons.flight_takeoff;
        label = 'Waiting...';
        break;
      case TrackingState.inFlight:
        bgColor = colorScheme.error;
        fgColor = colorScheme.onError;
        icon = Icons.stop_rounded;
        label = 'Stop';
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

// ── Section Header ──

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color statusColor;
  final String statusLabel;

  const _SectionHeader({
    required this.icon,
    required this.label,
    required this.statusColor,
    required this.statusLabel,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        children: [
          Icon(icon, size: 16, color: theme.colorScheme.primary),
          const SizedBox(width: 6),
          Text(label,
              style: theme.textTheme.labelLarge?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: statusColor.withAlpha(30),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.circle, size: 8, color: statusColor),
                const SizedBox(width: 4),
                Text(statusLabel,
                    style: theme.textTheme.labelSmall?.copyWith(
                      color: statusColor,
                    )),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── GPS Stats Card ──

class _GpsStatsCard extends StatelessWidget {
  final TrackingService tracking;
  final AuthService auth;

  const _GpsStatsCard({required this.tracking, required this.auth});

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

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Table(
          columnWidths: const {
            0: FlexColumnWidth(1),
            1: FlexColumnWidth(1),
          },
          children: [
            _buildRow(
              Icons.height, 'Altitude',
              UnitConverter.formatAltitude(pos?.alt, altUnit),
              Icons.speed, 'Speed',
              UnitConverter.formatSpeed(pos?.speed, speedUnit),
              context,
            ),
            _buildRow(
              Icons.cloud_upload, 'Points Sent',
              '${tracking.positionCount}',
              Icons.gps_fixed, 'Accuracy',
              pos?.accuracy != null ? '${pos!.accuracy!.toStringAsFixed(1)} m' : '--',
              context,
            ),
            _buildRow(
              Icons.tune, 'GPS Rate',
              tracking.isInFlight ? _zoneLabel(tracking.currentZone) : '--',
              Icons.flag, 'Nearest TP',
              tracking.inCompetitionMode
                  ? _nearestTpLabel(tracking.nearestTurnpointDistance)
                  : 'Free flight',
              context,
            ),
          ],
        ),
      ),
    );
  }

  TableRow _buildRow(
    IconData icon1, String label1, String value1,
    IconData icon2, String label2, String value2,
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

// ── Mesh Stats Card ──

class _MeshStatsCard extends StatelessWidget {
  final BleService ble;

  const _MeshStatsCard({required this.ble});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (!ble.isConnected) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              Icon(Icons.bluetooth_disabled,
                  color: theme.colorScheme.onSurfaceVariant, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  'No Meshtastic device paired.\nGo to Settings to connect.',
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    final ds = ble.deviceState;

    // Map Meshtastic device role to Aervyx profile name
    String profileName;
    IconData profileIcon;
    switch (ds.role) {
      case DeviceRole.tracker:
        profileName = 'Pilot';
        profileIcon = Icons.flight; // placeholder, overridden with custom widget below
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

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
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
              ],
            ),
            const Divider(height: 16),
            // Mesh stats grid
            Table(
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
                        icon: profileIcon,
                        label: 'Profile',
                        value: profileName,
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.cell_tower,
                        label: 'Channel',
                        value: ds.channelName.isNotEmpty
                            ? ds.channelName
                            : '--',
                      ),
                    ),
                  ],
                ),
                TableRow(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.radio,
                        label: 'Modem',
                        value: ds.modemPreset.label,
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.route,
                        label: 'Hops',
                        value: '${ds.hopLimit}',
                      ),
                    ),
                  ],
                ),
                TableRow(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.gps_fixed,
                        label: 'GPS',
                        value: ds.gpsMode.label,
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.cloud_upload,
                        label: 'MQTT',
                        value: ds.mqttEnabled ? 'Connected' : 'Disconnected',
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

// ── Flight Time Display ──

class _FlightTimeDisplay extends StatelessWidget {
  final TrackingService tracking;

  const _FlightTimeDisplay({required this.tracking});

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
          color: isActive ? theme.colorScheme.primary : theme.colorScheme.onSurfaceVariant,
        ),
        const SizedBox(width: 6),
        Text(
          _formatDuration(duration),
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w600,
            fontFeatures: const [FontFeature.tabularFigures()],
            color: isActive ? theme.colorScheme.onSurface : theme.colorScheme.onSurfaceVariant,
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

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _StatTile({
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
        Icon(icon, size: 16, color: theme.colorScheme.primary),
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
