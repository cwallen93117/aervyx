import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:wifi_scan/wifi_scan.dart';

import '../models/meshtastic_protobufs.dart';
import '../services/ble_service.dart';

/// Dedicated Meshtastic device configuration screen.
///
/// Sections:
/// 1. BLE Scan / Connect
/// 2. Profile Quick Setup (Pilot / Driver / Driver Wi-Fi / Repeater)
/// 3. Device Info (long name, short name)
/// 4. Wi-Fi
/// 5. Position & GPS
/// 6. LoRa Radio
/// 7. Channels & MQTT
/// 8. Advanced (power, telemetry, display, reboot)
class MeshtasticSettingsScreen extends StatelessWidget {
  const MeshtasticSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Meshtastic Settings'),
        actions: [
          if (ble.isConnected)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: Icon(Icons.circle, size: 12, color: Colors.green),
            ),
        ],
      ),
      body: Builder(
        builder: (context) => ListView(
          padding: EdgeInsets.fromLTRB(
              16, 16, 16, 16 + MediaQuery.of(context).padding.bottom),
          children: [
          // ── BLE Connection ──
          _BleConnectionSection(),

          if (ble.isConnected) ...[
            const SizedBox(height: 24),

            // ── Profile Quick Setup ──
            Row(
              children: [
                Expanded(child: _SectionHeader(title: 'Profile Quick Setup')),
                IconButton(
                  icon: const Icon(Icons.info_outline, size: 20),
                  tooltip: 'Compare profiles',
                  onPressed: () => _showProfileComparison(context),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _ProfileSelector(),

            const SizedBox(height: 24),

            // ── Device Info ──
            _SectionHeader(title: 'Device Info'),
            const SizedBox(height: 8),
            _DeviceInfoSection(),

            const SizedBox(height: 24),

            // ── Wi-Fi ──
            _SectionHeader(title: 'Wi-Fi'),
            const SizedBox(height: 8),
            _WifiSection(),

            const SizedBox(height: 24),

            // ── Position & GPS ──
            _SectionHeader(title: 'Position & GPS'),
            const SizedBox(height: 8),
            _PositionSection(),

            const SizedBox(height: 24),

            // ── LoRa Radio ──
            _SectionHeader(title: 'LoRa Radio'),
            const SizedBox(height: 8),
            _LoraSection(),

            const SizedBox(height: 24),

            // ── MQTT (configured by platform) ──
            _SectionHeader(title: 'MQTT'),
            const SizedBox(height: 8),
            _MqttInfoCard(),

            const SizedBox(height: 24),

            // ── Advanced ──
            _SectionHeader(title: 'Advanced'),
            const SizedBox(height: 8),
            _AdvancedSection(),

            const SizedBox(height: 32),
          ],
        ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Profile comparison dialog
// ═══════════════════════════════════════════════════════════════════════════════

const double _kRowHeight = 40.0;

void _showProfileComparison(BuildContext context) {
  final profiles = ProfileConfig.presets;
  final entries = [
    MeshtasticProfile.pilot,
    MeshtasticProfile.driver,
    MeshtasticProfile.driverWifi,
    MeshtasticProfile.repeater,
  ];

  String fmtBool(bool v) => v ? 'On' : 'Off';
  String fmtSecs(int s) {
    if (s >= 86400) return '${s ~/ 86400}d';
    if (s >= 3600) return '${s ~/ 3600}h';
    if (s >= 60) return '${s ~/ 60}min';
    return '${s}s';
  }
  String fmtDisplay(int s) => s == 0 ? 'Default' : '${s}s';

  final rows = <_CompRow>[
    _CompRow('Role', (c) => c.role.label),
    _CompRow('Rebroadcast', (c) => c.rebroadcastMode.label),
    _CompRow('Power saving', (c) => fmtBool(c.powerSaving)),
    _CompRow('GPS mode', (c) => c.gpsMode.label),
    _CompRow('Position interval', (c) => fmtSecs(c.positionBroadcastSecs)),
    _CompRow('Smart position', (c) => fmtBool(c.smartPositionEnabled),
        info: 'When enabled, the device sends position updates early if it '
            'detects significant movement based on the min distance and min '
            'interval thresholds, rather than waiting for the full broadcast '
            'interval. Helps capture turns and altitude changes in flight.'),
    _CompRow('Smart min distance', (c) => '${c.smartMinDistance}m'),
    _CompRow('Smart min interval', (c) => '${c.smartMinInterval}s'),
    _CompRow('Modem preset', (c) => c.modemPreset.label),
    _CompRow('Hop limit', (c) => '${c.hopLimit}'),
    _CompRow('Bluetooth', (c) => fmtBool(c.bluetoothEnabled)),
    _CompRow('Wi-Fi', (c) => fmtBool(c.wifiEnabled)),
    _CompRow('Display timeout', (c) => fmtDisplay(c.displayTimeoutSecs)),
    _CompRow('Telemetry interval', (c) => fmtSecs(c.telemetryIntervalSecs)),
  ];

  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    builder: (ctx) {
      final theme = Theme.of(ctx);
      return DraggableScrollableSheet(
        initialChildSize: 0.7,
        minChildSize: 0.4,
        maxChildSize: 0.95,
        expand: false,
        builder: (_, controller) => Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
              child: Text('Profile Comparison',
                  style: theme.textTheme.titleMedium),
            ),
            Expanded(
              child: SingleChildScrollView(
                controller: controller,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // ── Frozen label column ──
                    SizedBox(
                      width: 120,
                      child: Column(
                        children: [
                          _LabelCell(
                            label: 'Setting',
                            isHeader: true,
                            theme: theme,
                          ),
                          ...rows.map((row) => _LabelCell(
                            label: row.label,
                            isHeader: false,
                            theme: theme,
                            info: row.info,
                          )),
                        ],
                      ),
                    ),
                    // ── Scrollable value columns ──
                    Expanded(
                      child: SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: SizedBox(
                          width: entries.length * 90.0,
                          child: Column(
                            children: [
                              _ValueRow(
                                values: entries.map((p) => p.label).toList(),
                                isHeader: true,
                                theme: theme,
                              ),
                              ...rows.map((row) => _ValueRow(
                                values: entries.map((p) {
                                  final config = profiles[p]!;
                                  return row.getter(config);
                                }).toList(),
                                isHeader: false,
                                theme: theme,
                              )),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
    },
  );
}

/// A single cell in the frozen label column of the comparison table.
class _LabelCell extends StatelessWidget {
  final String label;
  final bool isHeader;
  final ThemeData theme;
  final String? info;

  const _LabelCell({
    required this.label,
    required this.isHeader,
    required this.theme,
    this.info,
  });

  @override
  Widget build(BuildContext context) {
    final labelStyle = isHeader
        ? theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.bold)
        : theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w500);
    final borderSide = BorderSide(
      color: theme.dividerColor.withValues(alpha: 0.3),
      width: 0.5,
    );

    return Container(
      height: _kRowHeight,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: isHeader
            ? theme.colorScheme.surfaceContainerHighest
            : theme.colorScheme.surfaceContainerLow,
        border: Border(bottom: borderSide, right: borderSide),
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(label, style: labelStyle, overflow: TextOverflow.ellipsis),
          ),
          if (info != null)
            GestureDetector(
              onTap: () => _showCompInfoDialog(context, label, info!),
              child: Padding(
                padding: const EdgeInsets.only(left: 4),
                child: Icon(Icons.info_outline,
                    size: 14, color: theme.colorScheme.primary),
              ),
            ),
        ],
      ),
    );
  }
}

/// A row of value cells in the scrollable area of the comparison table.
class _ValueRow extends StatelessWidget {
  final List<String> values;
  final bool isHeader;
  final ThemeData theme;

  const _ValueRow({
    required this.values,
    required this.isHeader,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    final valueStyle = isHeader
        ? theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.bold)
        : theme.textTheme.bodySmall;
    final borderSide = BorderSide(
      color: theme.dividerColor.withValues(alpha: 0.3),
      width: 0.5,
    );

    return Container(
      height: _kRowHeight,
      decoration: BoxDecoration(
        color: isHeader ? theme.colorScheme.surfaceContainerHighest : null,
        border: Border(bottom: borderSide),
      ),
      child: Row(
        children: values.map((v) => Container(
          width: 90,
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
          alignment: Alignment.center,
          child: Text(v, style: valueStyle, textAlign: TextAlign.center),
        )).toList(),
      ),
    );
  }
}

void _showCompInfoDialog(BuildContext context, String title, String body) {
  showDialog(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title, style: Theme.of(ctx).textTheme.titleSmall),
      content: Text(body, style: Theme.of(ctx).textTheme.bodySmall),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('OK')),
      ],
    ),
  );
}

class _CompRow {
  final String label;
  final String Function(ProfileConfig) getter;
  final String? info;
  const _CompRow(this.label, this.getter, {this.info});
}

// ═══════════════════════════════════════════════════════════════════════════════
// Section header
// ═══════════════════════════════════════════════════════════════════════════════

class _SectionHeader extends StatelessWidget {
  final String title;
  const _SectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleSmall?.copyWith(
            color: Theme.of(context).colorScheme.primary,
          ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// BLE Connection — scan, pair, disconnect
// ═══════════════════════════════════════════════════════════════════════════════

class _BleConnectionSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Scan button
        Row(
          children: [
            Expanded(
              child: FilledButton.icon(
                onPressed: ble.isScanning ? null : () => ble.startScan(),
                icon: const Icon(Icons.bluetooth_searching),
                label:
                    Text(ble.isScanning ? 'Scanning...' : 'Scan for Devices'),
              ),
            ),
            if (ble.isScanning) ...[
              const SizedBox(width: 12),
              IconButton(
                onPressed: () => ble.stopScan(),
                icon: const Icon(Icons.stop),
                tooltip: 'Stop scan',
              ),
            ],
          ],
        ),

        if (ble.error != null) ...[
          const SizedBox(height: 12),
          Text(ble.error!, style: TextStyle(color: theme.colorScheme.error)),
        ],
        if (ble.statusMessage != null) ...[
          const SizedBox(height: 12),
          Text(ble.statusMessage!, style: const TextStyle(color: Colors.green)),
        ],

        const SizedBox(height: 12),

        // Connected device
        if (ble.isConnected) ...[
          Card(
            color: theme.colorScheme.primaryContainer,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(Icons.bluetooth_connected,
                      color: theme.colorScheme.onPrimaryContainer),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          ble.deviceDisplayName,
                          style: theme.textTheme.titleSmall?.copyWith(
                            color: theme.colorScheme.onPrimaryContainer,
                          ),
                        ),
                        if (ble.deviceState.firmwareVersion != null)
                          Text(
                            'FW: ${ble.deviceState.firmwareVersion}',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onPrimaryContainer
                                  .withAlpha(180),
                            ),
                          ),
                      ],
                    ),
                  ),
                  OutlinedButton(
                    onPressed: () => ble.disconnect(),
                    child: const Text('Disconnect'),
                  ),
                ],
              ),
            ),
          ),
        ],

        // Discovered devices
        if (!ble.isConnected && ble.discoveredDevices.isNotEmpty) ...[
          ...ble.discoveredDevices.map((device) {
            return ListTile(
              leading: const Icon(Icons.bluetooth),
              title: Text(device.name),
              subtitle: Text('RSSI: ${device.rssi} dBm'),
              trailing: OutlinedButton(
                onPressed:
                    ble.isConnecting ? null : () => ble.connectToDevice(device),
                child: Text(ble.isConnecting ? 'Connecting...' : 'Pair'),
              ),
            );
          }),
        ] else if (!ble.isConnected) ...[
          SizedBox(
            width: double.infinity,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'No Meshtastic devices found.\nTap Scan to search.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Profile Quick Setup
// ═══════════════════════════════════════════════════════════════════════════════

/// Custom hang glider icon — delta wing with pilot.
class _HangGliderIcon extends StatelessWidget {
  final double size;
  final Color? color;
  const _HangGliderIcon({this.size = 20, this.color});

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size(size, size),
      painter: _HangGliderPainter(
        color: color ?? Theme.of(context).colorScheme.onSurface,
      ),
    );
  }
}

class _HangGliderPainter extends CustomPainter {
  final Color color;
  _HangGliderPainter({required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;

    final w = size.width;
    final h = size.height;

    // Delta wing (triangle)
    final wing = Path()
      ..moveTo(w * 0.5, h * 0.15) // nose
      ..lineTo(w * 0.02, h * 0.55) // left wingtip
      ..lineTo(w * 0.98, h * 0.55) // right wingtip
      ..close();
    canvas.drawPath(wing, paint);

    // Control bar (A-frame) lines
    final linePaint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    // Left bar
    canvas.drawLine(
      Offset(w * 0.5, h * 0.35),
      Offset(w * 0.35, h * 0.75),
      linePaint,
    );
    // Right bar
    canvas.drawLine(
      Offset(w * 0.5, h * 0.35),
      Offset(w * 0.65, h * 0.75),
      linePaint,
    );
    // Base bar
    canvas.drawLine(
      Offset(w * 0.35, h * 0.75),
      Offset(w * 0.65, h * 0.75),
      linePaint,
    );

    // Pilot (small circle)
    canvas.drawCircle(
      Offset(w * 0.5, h * 0.85),
      w * 0.06,
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _ProfileSelector extends StatelessWidget {
  static const _profileIcons = {
    MeshtasticProfile.driver: Icons.directions_car,
    MeshtasticProfile.driverWifi: Icons.wifi,
    MeshtasticProfile.repeater: Icons.cell_tower,
  };

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Apply a preset profile to configure all settings at once.',
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            ...MeshtasticProfile.values.map((profile) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: OutlinedButton(
                  onPressed: ble.isPushingConfig
                      ? null
                      : () => _confirmApply(context, ble, profile),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 16, vertical: 12),
                  ),
                  child: Row(
                    children: [
                      profile == MeshtasticProfile.pilot
                          ? const _HangGliderIcon(size: 20)
                          : Icon(_profileIcons[profile], size: 20),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(profile.label,
                            style: theme.textTheme.titleSmall),
                      ),
                      const Icon(Icons.arrow_forward_ios, size: 14),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  void _confirmApply(
      BuildContext context, BleService ble, MeshtasticProfile profile) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Apply ${profile.label} profile?'),
        content: const Text(
          'This will overwrite all device settings and reboot the device.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              ble.applyProfile(profile);
            },
            child: const Text('Apply'),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Device Info — long name, short name
// ═══════════════════════════════════════════════════════════════════════════════

class _DeviceInfoSection extends StatefulWidget {
  @override
  State<_DeviceInfoSection> createState() => _DeviceInfoSectionState();
}

class _DeviceInfoSectionState extends State<_DeviceInfoSection> {
  late TextEditingController _longNameCtl;
  late TextEditingController _shortNameCtl;

  @override
  void initState() {
    super.initState();
    final state = context.read<BleService>().deviceState;
    _longNameCtl = TextEditingController(text: state.longName);
    _shortNameCtl = TextEditingController(text: state.shortName);
  }

  @override
  void dispose() {
    _longNameCtl.dispose();
    _shortNameCtl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            TextField(
              controller: _longNameCtl,
              decoration: const InputDecoration(
                labelText: 'Long Name',
                border: OutlineInputBorder(),
                hintText: 'e.g. Pilot-Jones',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _shortNameCtl,
              maxLength: 4,
              decoration: const InputDecoration(
                labelText: 'Short Name (2-4 chars)',
                border: OutlineInputBorder(),
                hintText: 'e.g. PJ',
              ),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                onPressed: ble.isPushingConfig
                    ? null
                    : () => ble.setDeviceName(
                          longName: _longNameCtl.text.trim(),
                          shortName: _shortNameCtl.text.trim(),
                        ),
                child: const Text('Save Name'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Wi-Fi
// ═══════════════════════════════════════════════════════════════════════════════

class _WifiSection extends StatefulWidget {
  @override
  State<_WifiSection> createState() => _WifiSectionState();
}

class _WifiSectionState extends State<_WifiSection> {
  late TextEditingController _ssidCtl;
  late TextEditingController _pskCtl;
  bool _obscurePassword = true;
  bool _isScanning = false;
  bool _manualEntry = false;
  List<WiFiAccessPoint> _networks = [];
  String? _scanError;

  @override
  void initState() {
    super.initState();
    final state = context.read<BleService>().deviceState;
    _ssidCtl = TextEditingController(text: state.wifiSsid);
    _pskCtl = TextEditingController(text: state.wifiPsk);
  }

  @override
  void dispose() {
    _ssidCtl.dispose();
    _pskCtl.dispose();
    super.dispose();
  }

  Future<void> _scanNetworks() async {
    setState(() {
      _isScanning = true;
      _scanError = null;
    });

    try {
      final canScan = await WiFiScan.instance.canStartScan();
      if (canScan != CanStartScan.yes) {
        setState(() {
          _scanError = 'Cannot scan: $canScan. Check location permissions.';
          _isScanning = false;
        });
        return;
      }

      await WiFiScan.instance.startScan();
      final canGet = await WiFiScan.instance.canGetScannedResults();
      if (canGet != CanGetScannedResults.yes) {
        setState(() {
          _scanError = 'Cannot get results: $canGet';
          _isScanning = false;
        });
        return;
      }

      final results = await WiFiScan.instance.getScannedResults();
      // Sort by signal strength, remove duplicates
      final seen = <String>{};
      final unique = <WiFiAccessPoint>[];
      results.sort((a, b) => b.level.compareTo(a.level));
      for (final ap in results) {
        if (ap.ssid.isNotEmpty && seen.add(ap.ssid)) {
          unique.add(ap);
        }
      }

      setState(() {
        _networks = unique;
        _isScanning = false;
      });
    } catch (e) {
      setState(() {
        _scanError = 'Scan failed: $e';
        _isScanning = false;
      });
    }
  }

  void _selectNetwork(String ssid) {
    setState(() {
      _ssidCtl.text = ssid;
      _networks = []; // Collapse the list
    });
  }

  IconData _signalIcon(int level) {
    if (level >= -50) return Icons.signal_wifi_4_bar;
    if (level >= -60) return Icons.network_wifi_3_bar;
    if (level >= -70) return Icons.network_wifi_2_bar;
    if (level >= -80) return Icons.network_wifi_1_bar;
    return Icons.signal_wifi_0_bar;
  }

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final ds = ble.deviceState;
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.wifi, size: 20, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Wi-Fi', style: theme.textTheme.bodyMedium),
                ),
                Switch(
                  value: ds.wifiEnabled,
                  onChanged: ble.isPushingConfig
                      ? null
                      : (v) => ble.setWifi(enabled: v),
                ),
              ],
            ),
            if (ds.wifiEnabled) ...[
              const SizedBox(height: 12),

              // Current network display
              if (ds.wifiSsid.isNotEmpty) ...[
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primaryContainer.withAlpha(80),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(Icons.wifi, size: 16,
                          color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Text('Current: ${ds.wifiSsid}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          )),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
              ],

              // Scan / Manual toggle
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _isScanning ? null : _scanNetworks,
                      icon: _isScanning
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.wifi_find, size: 18),
                      label: Text(
                          _isScanning ? 'Scanning...' : 'Scan Networks'),
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton(
                    onPressed: () =>
                        setState(() => _manualEntry = !_manualEntry),
                    child: Text(_manualEntry ? 'Hide' : 'Manual'),
                  ),
                ],
              ),

              if (_scanError != null) ...[
                const SizedBox(height: 8),
                Text(_scanError!,
                    style: TextStyle(
                        color: theme.colorScheme.error, fontSize: 12)),
              ],

              // Scanned networks list
              if (_networks.isNotEmpty) ...[
                const SizedBox(height: 12),
                Text('Available Networks',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    )),
                const SizedBox(height: 4),
                Container(
                  constraints: const BoxConstraints(maxHeight: 200),
                  decoration: BoxDecoration(
                    border: Border.all(
                        color: theme.colorScheme.outlineVariant),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _networks.length,
                    separatorBuilder: (_, __) =>
                        const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final ap = _networks[index];
                      final isSelected = _ssidCtl.text == ap.ssid;
                      return ListTile(
                        dense: true,
                        leading: Icon(
                          _signalIcon(ap.level),
                          size: 20,
                          color: isSelected
                              ? theme.colorScheme.primary
                              : null,
                        ),
                        title: Text(
                          ap.ssid,
                          style: TextStyle(
                            fontWeight: isSelected
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                        subtitle: Text(
                          '${ap.level} dBm',
                          style: theme.textTheme.bodySmall,
                        ),
                        trailing: isSelected
                            ? Icon(Icons.check_circle,
                                color: theme.colorScheme.primary,
                                size: 20)
                            : null,
                        onTap: () => _selectNetwork(ap.ssid),
                      );
                    },
                  ),
                ),
              ],

              // Manual SSID entry
              if (_manualEntry || _networks.isEmpty) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _ssidCtl,
                  decoration: const InputDecoration(
                    labelText: 'SSID',
                    border: OutlineInputBorder(),
                    hintText: 'Wi-Fi network name',
                  ),
                ),
              ],

              // Password + Save (always visible when Wi-Fi enabled)
              const SizedBox(height: 12),
              TextField(
                controller: _pskCtl,
                obscureText: _obscurePassword,
                decoration: InputDecoration(
                  labelText: 'Password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscurePassword
                        ? Icons.visibility_off
                        : Icons.visibility),
                    onPressed: () =>
                        setState(() => _obscurePassword = !_obscurePassword),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: ble.isPushingConfig || _ssidCtl.text.trim().isEmpty
                      ? null
                      : () => ble.setWifi(
                            enabled: true,
                            ssid: _ssidCtl.text.trim(),
                            password: _pskCtl.text,
                          ),
                  icon: const Icon(Icons.save, size: 18),
                  label: Text(_ssidCtl.text.trim().isEmpty
                      ? 'Select a network'
                      : 'Save Wi-Fi: ${_ssidCtl.text.trim()}'),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Position & GPS (read-only display of current config)
// ═══════════════════════════════════════════════════════════════════════════════

class _PositionSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ds = context.watch<BleService>().deviceState;
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _ConfigRow(
                label: 'GPS Mode', value: ds.gpsMode.label, theme: theme),
            _ConfigRow(
                label: 'Broadcast Interval',
                value: '${ds.positionBroadcastSecs}s',
                theme: theme),
            _ConfigRow(
                label: 'Smart Position',
                value: ds.smartPositionEnabled ? 'ON' : 'OFF',
                theme: theme),
            if (ds.smartPositionEnabled) ...[
              _ConfigRow(
                  label: '  Min Distance',
                  value: '${ds.smartMinDistance} m',
                  theme: theme),
              _ConfigRow(
                  label: '  Min Interval',
                  value: '${ds.smartMinInterval}s',
                  theme: theme),
            ],
            _ConfigRow(
                label: 'Position Flags',
                value: _describeFlags(ds.positionFlags),
                theme: theme),
          ],
        ),
      ),
    );
  }

  String _describeFlags(int flags) {
    final parts = <String>[];
    if (flags & PositionFlags.altitude != 0) parts.add('Alt');
    if (flags & PositionFlags.altitudeMsl != 0) parts.add('MSL');
    if (flags & PositionFlags.heading != 0) parts.add('Heading');
    if (flags & PositionFlags.speed != 0) parts.add('Speed');
    if (flags & PositionFlags.dop != 0) parts.add('DOP');
    if (flags & PositionFlags.satInView != 0) parts.add('Sats');
    return parts.isEmpty ? 'None' : parts.join(', ');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// LoRa Radio
// ═══════════════════════════════════════════════════════════════════════════════

class _LoraSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final ds = ble.deviceState;
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            // Region selector
            Row(
              children: [
                Expanded(
                    child: Text('Region', style: theme.textTheme.bodyMedium)),
                DropdownButton<RegionCode>(
                  value: ds.region,
                  onChanged: ble.isPushingConfig
                      ? null
                      : (v) {
                          if (v != null) ble.setLoraRegion(v);
                        },
                  items: RegionCode.values
                      .map((r) => DropdownMenuItem(
                            value: r,
                            child: Text(r.label),
                          ))
                      .toList(),
                ),
              ],
            ),
            const Divider(height: 16),
            _ConfigRow(
                label: 'Modem Preset',
                value: ds.modemPreset.label,
                theme: theme),
            _ConfigRow(
                label: 'Hop Limit',
                value: '${ds.hopLimit}',
                theme: theme),
            _ConfigRow(
                label: 'TX Enabled',
                value: ds.txEnabled ? 'Yes' : 'No',
                theme: theme),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// MQTT (read-only — configured by platform admin)
// ═══════════════════════════════════════════════════════════════════════════════

class _MqttInfoCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ds = context.watch<BleService>().deviceState;
    final theme = Theme.of(context);
    final broker = ds.mqttAddress.isNotEmpty ? ds.mqttAddress : 'mqtt.meshtastic.org';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.cloud_upload,
                    size: 20, color: theme.colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text('Configured by platform',
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      )),
                ),
              ],
            ),
            const SizedBox(height: 8),
            _ConfigRow(label: 'Broker', value: broker, theme: theme),
            _ConfigRow(
                label: 'Root Topic',
                value: ds.mqttRootTopic.isNotEmpty ? ds.mqttRootTopic : 'msh',
                theme: theme),
            _ConfigRow(
                label: 'Encryption',
                value: ds.mqttEncryptionEnabled ? 'Enabled' : 'Disabled',
                theme: theme),
          ],
        ),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Advanced — power, telemetry, display, reboot
// ═══════════════════════════════════════════════════════════════════════════════

class _AdvancedSection extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final ds = ble.deviceState;
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _ConfigRow(
                label: 'Device Role', value: ds.role.label, theme: theme),
            _ConfigRow(
                label: 'Rebroadcast',
                value: ds.rebroadcastMode.label,
                theme: theme),
            _ConfigRow(
                label: 'Power Saving',
                value: ds.isPowerSaving ? 'ON' : 'OFF',
                theme: theme),
            _ConfigRow(
                label: 'Bluetooth',
                value: ds.bluetoothEnabled ? 'ON' : 'OFF',
                theme: theme),
            _ConfigRow(
                label: 'BLE Pairing',
                value: ds.blePairingMode.label,
                theme: theme),
            _ConfigRow(
                label: 'Display Timeout',
                value: ds.screenOnSecs == 0
                    ? 'Off'
                    : '${ds.screenOnSecs}s',
                theme: theme),
            _ConfigRow(
                label: 'Telemetry Interval',
                value: '${ds.telemetryDeviceInterval}s',
                theme: theme),
            _ConfigRow(
                label: 'Store & Forward',
                value: ds.storeForwardEnabled
                    ? (ds.storeForwardIsServer ? 'Server' : 'Client')
                    : 'OFF',
                theme: theme),
            _ConfigRow(
                label: 'Neighbor Info',
                value: ds.neighborInfoEnabled ? 'ON' : 'OFF',
                theme: theme),
            _ConfigRow(
                label: 'Channel Uplink',
                value: ds.channelUplinkEnabled ? 'ON' : 'OFF',
                theme: theme),
            const Divider(height: 24),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: ble.isPushingConfig
                    ? null
                    : () => _confirmReboot(context, ble),
                icon: const Icon(Icons.restart_alt, size: 18),
                label: const Text('Reboot Device'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: theme.colorScheme.error,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _confirmReboot(BuildContext context, BleService ble) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Reboot device?'),
        content: const Text('The device will restart in 5 seconds.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              Navigator.pop(ctx);
              ble.rebootDevice();
            },
            child: const Text('Reboot'),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Config row helper
// ═══════════════════════════════════════════════════════════════════════════════

class _ConfigRow extends StatelessWidget {
  final String label;
  final String value;
  final ThemeData theme;

  const _ConfigRow({
    required this.label,
    required this.value,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: theme.textTheme.bodyMedium),
          Text(value,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
              )),
        ],
      ),
    );
  }
}
