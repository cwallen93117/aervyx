import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/tracking_service.dart';
import '../widgets/aervyx_logo.dart';
import 'flights_screen.dart';
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
            Text(
              'Aervyx',
              style: TextStyle(
                fontWeight: FontWeight.w700,
                color: AervyxLogo.cyan,
              ),
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

              // Big tracking button — near top of screen
              SizedBox(
                width: 180,
                height: 180,
                child: FilledButton(
                  onPressed: () {
                    if (tracking.isTracking) {
                      tracking.stopTracking();
                    } else {
                      tracking.startTracking();
                    }
                  },
                  style: FilledButton.styleFrom(
                    shape: const CircleBorder(),
                    backgroundColor: tracking.isTracking
                        ? colorScheme.error
                        : colorScheme.primary,
                    foregroundColor: tracking.isTracking
                        ? colorScheme.onError
                        : colorScheme.onPrimary,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        tracking.isTracking
                            ? Icons.stop_rounded
                            : Icons.play_arrow_rounded,
                        size: 56,
                      ),
                      const SizedBox(height: 4),
                      Text(
                        tracking.isTracking ? 'Stop' : 'Start',
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

              const SizedBox(height: 8),

              // Flight time — right below the button
              _FlightTimeDisplay(tracking: tracking),

              const SizedBox(height: 8),

              // SOS button
              _SosButton(ble: ble),

              const SizedBox(height: 12),

              // ── Stats ──
              // GPS stats card
              _SectionHeader(
                icon: Icons.gps_fixed,
                label: 'GPS',
                statusColor: tracking.isTracking ? Colors.green : Colors.grey,
                statusLabel: tracking.isTracking ? 'Active' : 'Off',
              ),
              _GpsStatsCard(tracking: tracking),

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
              if (tracking.error != null)
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

  const _GpsStatsCard({required this.tracking});

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
              pos?.alt != null ? '${pos!.alt!.toStringAsFixed(0)} m' : '--',
              Icons.speed, 'Speed',
              pos?.speed != null ? '${(pos!.speed! * 3.6).toStringAsFixed(1)} km/h' : '--',
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
              tracking.isTracking ? _zoneLabel(tracking.currentZone) : '--',
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
    final theme = Theme.of(context);
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

    final info = ble.nodeInfo;

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
                  ble.connectedDevice!.name,
                  style: theme.textTheme.labelMedium?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (info?.firmwareVersion != null) ...[
                  const SizedBox(width: 8),
                  Text(
                    'v${info!.firmwareVersion}',
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
                        icon: Icons.people,
                        label: 'Peers Online',
                        value: info != null ? '${info.connectedPeers}' : '--',
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.signal_cellular_alt,
                        label: 'Signal',
                        value: info?.signalStrength != null
                            ? '${info!.signalStrength} dBm'
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
                        icon: Icons.hearing,
                        label: 'SNR',
                        value: info?.snr != null
                            ? '${info!.snr!.toStringAsFixed(1)} dB'
                            : '--',
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.cell_tower,
                        label: 'Channel',
                        value: info?.channelName ?? '--',
                      ),
                    ),
                  ],
                ),
                TableRow(
                  children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.battery_std,
                        label: 'Radio Battery',
                        value: info?.deviceBattery != null
                            ? '${info!.deviceBattery}%'
                            : '--',
                      ),
                    ),
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 6),
                      child: _StatTile(
                        icon: Icons.air,
                        label: 'Air Util TX',
                        value: info?.airUtilTx != null
                            ? '${info!.airUtilTx}%'
                            : '--',
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
    final isActive = tracking.isTracking;

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
    final theme = Theme.of(context);

    return SizedBox(
      width: double.infinity,
      height: 44,
      child: OutlinedButton.icon(
        onPressed: ble.isSendingSos ? null : () => _confirmSos(context),
        icon: const SizedBox.shrink(),
        label: Text(
          ble.isSendingSos ? 'Sending...' : 'Send SOS',
          style: TextStyle(
            color: ble.isSendingSos ? null : Colors.red,
            fontWeight: FontWeight.bold,
          ),
        ),
        style: OutlinedButton.styleFrom(
          side: const BorderSide(color: Colors.red, width: 1.5),
        ),
      ),
    );
  }

  void _confirmSos(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.sos, color: Colors.red),
            SizedBox(width: 8),
            Text('Send SOS?'),
          ],
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
