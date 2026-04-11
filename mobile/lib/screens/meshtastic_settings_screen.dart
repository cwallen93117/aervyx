import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:wifi_scan/wifi_scan.dart';

import '../models/meshtastic_protobufs.dart';
import '../services/ble_service.dart';

/// Meshtastic device configuration screen — simplified for pilots and drivers.
///
/// Sections:
/// 1. BLE Scan / Connect
/// 2. Settings (user-editable: role, name, region, wi-fi for Driver role)
/// 3. Admin Settings (read-only profile values)
/// 4. Reboot
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
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 12),
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

              // ── Settings ──
              const _SectionHeader(title: 'Settings'),
              const SizedBox(height: 8),
              _SettingsCard(),

              const SizedBox(height: 24),

              // ── Admin Settings ──
              const _SectionHeader(title: 'Admin Settings'),
              const SizedBox(height: 8),
              _AdminSettingsCard(),

              const SizedBox(height: 32),
            ],
          ],
        ),
      ),
    );
  }
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
// Settings card — role, name, region, wi-fi (driver only)
// ═══════════════════════════════════════════════════════════════════════════════

class _SettingsCard extends StatefulWidget {
  @override
  State<_SettingsCard> createState() => _SettingsCardState();
}

class _SettingsCardState extends State<_SettingsCard> {
  // Role: true = Pilot, false = Driver / Base Station
  bool _isPilot = true;

  late TextEditingController _longNameCtl;
  late TextEditingController _shortNameCtl;
  late RegionCode _region;

  // Wi-Fi (Driver only)
  late TextEditingController _ssidCtl;
  late TextEditingController _pskCtl;
  bool _obscurePassword = true;
  bool _wifiScanning = false;
  List<WiFiAccessPoint> _networks = [];
  String? _wifiScanError;

  @override
  void initState() {
    super.initState();
    final ds = context.read<BleService>().deviceState;
    _isPilot = ds.role != DeviceRole.router;
    _longNameCtl = TextEditingController(text: ds.longName);
    _shortNameCtl = TextEditingController(text: ds.shortName);
    _region = ds.region;
    _ssidCtl = TextEditingController(text: ds.wifiSsid);
    _pskCtl = TextEditingController(text: ds.wifiPsk);
  }

  @override
  void dispose() {
    _longNameCtl.dispose();
    _shortNameCtl.dispose();
    _ssidCtl.dispose();
    _pskCtl.dispose();
    super.dispose();
  }

  void _onRoleChanged(bool isPilot) {
    setState(() {
      _isPilot = isPilot;
      _networks = [];
      _wifiScanError = null;
    });
    final ble = context.read<BleService>();
    final profile =
        isPilot ? MeshtasticProfile.pilot : MeshtasticProfile.repeater;
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Apply ${isPilot ? "Pilot" : "Driver / Base Station"} profile?'),
        content: const Text(
          'This will overwrite all device settings and reboot the device.',
        ),
        actions: [
          TextButton(
            onPressed: () {
              // Revert toggle if user cancels
              setState(() => _isPilot = !isPilot);
              Navigator.pop(ctx);
            },
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

  Future<void> _scanNetworks() async {
    setState(() {
      _wifiScanning = true;
      _wifiScanError = null;
    });

    try {
      final canScan = await WiFiScan.instance.canStartScan();
      if (canScan != CanStartScan.yes) {
        setState(() {
          _wifiScanError = 'Cannot scan: $canScan. Check location permissions.';
          _wifiScanning = false;
        });
        return;
      }

      await WiFiScan.instance.startScan();
      final canGet = await WiFiScan.instance.canGetScannedResults();
      if (canGet != CanGetScannedResults.yes) {
        setState(() {
          _wifiScanError = 'Cannot get results: $canGet';
          _wifiScanning = false;
        });
        return;
      }

      final results = await WiFiScan.instance.getScannedResults();
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
        _wifiScanning = false;
      });
    } catch (e) {
      setState(() {
        _wifiScanError = 'Scan failed: $e';
        _wifiScanning = false;
      });
    }
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
    final theme = Theme.of(context);
    final disabled = ble.isPushingConfig;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // ── Device Role ──
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(
                  value: true,
                  label: Text('Pilot'),
                  icon: Icon(Icons.gps_fixed, size: 18),
                ),
                ButtonSegment(
                  value: false,
                  label: Text('Driver / Base Station'),
                  icon: Icon(Icons.cell_tower, size: 18),
                ),
              ],
              selected: {_isPilot},
              onSelectionChanged:
                  disabled ? null : (v) => _onRoleChanged(v.first),
            ),
            const SizedBox(height: 4),
            Text(
              _isPilot
                  ? 'Optimised for position tracking (pilots)'
                  : 'Always-on relay for mesh coverage (drivers & base stations)',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),

            const Divider(height: 32),

            // ── Long name ──
            TextField(
              controller: _longNameCtl,
              enabled: !disabled,
              decoration: const InputDecoration(
                labelText: 'Long Name',
                border: OutlineInputBorder(),
                hintText: 'e.g. Pilot-Jones',
              ),
            ),
            const SizedBox(height: 12),

            // ── Short name ──
            TextField(
              controller: _shortNameCtl,
              enabled: !disabled,
              maxLength: 4,
              decoration: const InputDecoration(
                labelText: 'Short Name (2–4 chars)',
                border: OutlineInputBorder(),
                hintText: 'e.g. PJ',
              ),
            ),
            const SizedBox(height: 4),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton(
                onPressed: disabled
                    ? null
                    : () => ble.setDeviceName(
                          longName: _longNameCtl.text.trim(),
                          shortName: _shortNameCtl.text.trim(),
                        ),
                child: const Text('Save Name'),
              ),
            ),

            const Divider(height: 32),

            // ── Region ──
            Row(
              children: [
                Expanded(
                    child: Text('Region', style: theme.textTheme.bodyMedium)),
                DropdownButton<RegionCode>(
                  value: _region,
                  onChanged: disabled
                      ? null
                      : (v) {
                          if (v != null) {
                            setState(() => _region = v);
                            ble.setLoraRegion(v);
                          }
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

            // ── Wi-Fi (Driver / Base Station only) ──
            if (!_isPilot) ...[
              const Divider(height: 32),
              Text('Wi-Fi', style: theme.textTheme.labelMedium?.copyWith(
                fontWeight: FontWeight.bold,
              )),
              const SizedBox(height: 12),

              // Scan button
              Row(
                children: [
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: disabled || _wifiScanning
                          ? null
                          : _scanNetworks,
                      icon: _wifiScanning
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(
                                  strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.wifi_find, size: 18),
                      label: Text(
                          _wifiScanning ? 'Scanning...' : 'Scan Networks'),
                    ),
                  ),
                ],
              ),

              if (_wifiScanError != null) ...[
                const SizedBox(height: 8),
                Text(_wifiScanError!,
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
                    border:
                        Border.all(color: theme.colorScheme.outlineVariant),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: _networks.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
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
                        subtitle: Text('${ap.level} dBm',
                            style: theme.textTheme.bodySmall),
                        trailing: isSelected
                            ? Icon(Icons.check_circle,
                                color: theme.colorScheme.primary, size: 20)
                            : null,
                        onTap: () =>
                            setState(() => _ssidCtl.text = ap.ssid),
                      );
                    },
                  ),
                ),
              ],

              const SizedBox(height: 12),

              // SSID field
              TextField(
                controller: _ssidCtl,
                enabled: !disabled,
                decoration: const InputDecoration(
                  labelText: 'SSID',
                  border: OutlineInputBorder(),
                  hintText: 'Wi-Fi network name',
                ),
              ),
              const SizedBox(height: 12),

              // Password field
              TextField(
                controller: _pskCtl,
                enabled: !disabled,
                obscureText: _obscurePassword,
                decoration: InputDecoration(
                  labelText: 'Password',
                  border: const OutlineInputBorder(),
                  suffixIcon: IconButton(
                    icon: Icon(_obscurePassword
                        ? Icons.visibility_off
                        : Icons.visibility),
                    onPressed: () => setState(
                        () => _obscurePassword = !_obscurePassword),
                  ),
                ),
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  onPressed: disabled || _ssidCtl.text.trim().isEmpty
                      ? null
                      : () => ble.setWifi(
                            enabled: true,
                            ssid: _ssidCtl.text.trim(),
                            password: _pskCtl.text,
                          ),
                  icon: const Icon(Icons.save, size: 18),
                  label: const Text('Save Wi-Fi'),
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
// Admin Settings card — read-only profile values
// ═══════════════════════════════════════════════════════════════════════════════

class _AdminSettingsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final ds = ble.deviceState;
    final theme = Theme.of(context);

    final broker =
        ds.mqttAddress.isNotEmpty ? ds.mqttAddress : 'mqtt.meshtastic.org';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Card subtitle
            Text(
              'Configured by your competition admin. Contact your scorer to change these.',
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),

            const Divider(height: 24),

            // ── Position ──
            _ConfigRow(
                label: 'Position interval',
                value: '${ds.positionBroadcastSecs}s',
                theme: theme),
            _ConfigRow(
                label: 'Smart position',
                value: ds.smartPositionEnabled ? 'Yes' : 'No',
                theme: theme),
            if (ds.smartPositionEnabled) ...[
              _ConfigRow(
                  label: 'Smart min distance',
                  value: '${ds.smartMinDistance} m',
                  theme: theme),
              _ConfigRow(
                  label: 'Smart min interval',
                  value: '${ds.smartMinInterval}s',
                  theme: theme),
            ],
            _ConfigRow(
                label: 'GPS mode', value: ds.gpsMode.label, theme: theme),

            const Divider(height: 24),

            // ── Display ──
            _ConfigRow(
                label: 'Display timeout',
                value: ds.screenOnSecs == 0 ? 'Always on' : '${ds.screenOnSecs}s',
                theme: theme),

            const Divider(height: 24),

            // ── LoRa ──
            _ConfigRow(
                label: 'LoRa modem preset',
                value: ds.modemPreset.label,
                theme: theme),
            _ConfigRow(
                label: 'Hop limit',
                value: '${ds.hopLimit}',
                theme: theme),
            _ConfigRow(
                label: 'Rebroadcast mode',
                value: ds.rebroadcastMode.label,
                theme: theme),
            _ConfigRow(
                label: 'TX enabled',
                value: ds.txEnabled ? 'Yes' : 'No',
                theme: theme),

            const Divider(height: 24),

            // ── MQTT ──
            _ConfigRow(
                label: 'MQTT enabled',
                value: ds.mqttEnabled ? 'Yes' : 'No',
                theme: theme),
            if (ds.mqttEnabled) ...[
              _ConfigRow(label: 'MQTT broker', value: broker, theme: theme),
              _ConfigRow(
                  label: 'MQTT topic prefix',
                  value: ds.mqttRootTopic.isNotEmpty ? ds.mqttRootTopic : 'msh',
                  theme: theme),
            ],

            const Divider(height: 24),

            // ── Bluetooth / Power ──
            _ConfigRow(
                label: 'Bluetooth enabled',
                value: ds.bluetoothEnabled ? 'Yes' : 'No',
                theme: theme),
            _ConfigRow(
                label: 'Power saving',
                value: ds.isPowerSaving ? 'Yes' : 'No',
                theme: theme),

            const Divider(height: 24),

            // ── Telemetry & modules ──
            _ConfigRow(
                label: 'Telemetry interval',
                value: '${ds.telemetryDeviceInterval}s',
                theme: theme),
            _ConfigRow(
                label: 'Store & Forward',
                value: ds.storeForwardEnabled
                    ? (ds.storeForwardIsServer ? 'Server' : 'Client')
                    : 'Off',
                theme: theme),
            _ConfigRow(
                label: 'Neighbor info',
                value: ds.neighborInfoEnabled ? 'On' : 'Off',
                theme: theme),
            _ConfigRow(
                label: 'Channel uplink',
                value: ds.channelUplinkEnabled ? 'On' : 'Off',
                theme: theme),

            const Divider(height: 24),

            // ── Reboot ──
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
// Config row helper — label / value pair
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
