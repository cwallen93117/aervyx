import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:wifi_scan/wifi_scan.dart';

import '../models/meshtastic_protobufs.dart';
import '../services/ble_service.dart';
import '../services/mesh_transport.dart';

/// Meshtastic device configuration screen — simplified for pilots and drivers.
///
/// Sections:
/// 1. BLE Scan / Connect
/// 2. Settings (user-editable: profile, region, name, wi-fi for Driver roles)
/// 3. Device Settings (collapsible read-only profile values)
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
            // ── Connection (Bluetooth / Network / Serial) ──
            _ConnectionSection(),

            if (ble.isConnected) ...[
              const SizedBox(height: 24),

              // ── Settings ──
              const _SectionHeader(title: 'Settings'),
              const SizedBox(height: 8),
              _SettingsCard(),

              const SizedBox(height: 24),

              // ── Device Settings (collapsible) ──
              _DeviceSettingsCard(),

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
// Connection — Bluetooth / Network / Serial tabs
// ═══════════════════════════════════════════════════════════════════════════════

class _ConnectionSection extends StatefulWidget {
  @override
  State<_ConnectionSection> createState() => _ConnectionSectionState();
}

class _ConnectionSectionState extends State<_ConnectionSection> {
  ConnectionType _selectedTab = ConnectionType.ble;
  final _ipController = TextEditingController();
  final _portController = TextEditingController(text: '4403');

  @override
  void dispose() {
    _ipController.dispose();
    _portController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    // Determine which tabs to show (Serial only on Android)
    final showSerial = Platform.isAndroid;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // ── Tab selector ──
        if (!ble.isConnected) ...[
          SizedBox(
            width: double.infinity,
            child: SegmentedButton<ConnectionType>(
              segments: [
                const ButtonSegment<ConnectionType>(
                  value: ConnectionType.ble,
                  icon: Icon(Icons.bluetooth, size: 18),
                  label: Text('Bluetooth'),
                ),
                const ButtonSegment<ConnectionType>(
                  value: ConnectionType.tcp,
                  icon: Icon(Icons.wifi, size: 18),
                  label: Text('Network'),
                ),
                if (showSerial)
                  const ButtonSegment<ConnectionType>(
                    value: ConnectionType.serial,
                    icon: Icon(Icons.usb, size: 18),
                    label: Text('Serial'),
                  ),
              ],
              selected: {_selectedTab},
              onSelectionChanged: (s) => setState(() => _selectedTab = s.first),
              showSelectedIcon: false,
            ),
          ),
          const SizedBox(height: 12),
        ],

        // ── Error / status messages ──
        if (ble.error != null) ...[
          Text(ble.error!, style: TextStyle(color: theme.colorScheme.error)),
          const SizedBox(height: 8),
        ],
        if (ble.statusMessage != null) ...[
          Text(ble.statusMessage!, style: const TextStyle(color: Colors.green)),
          const SizedBox(height: 8),
        ],

        // ── Connected device card (transport-aware) ──
        if (ble.isConnected) ...[
          _ConnectedDeviceCard(),
        ] else ...[
          // ── Per-tab content ──
          if (_selectedTab == ConnectionType.ble) _BluetoothTab(),
          if (_selectedTab == ConnectionType.tcp)
            _NetworkTab(
              ipController: _ipController,
              portController: _portController,
            ),
          if (_selectedTab == ConnectionType.serial && showSerial)
            _SerialTab(),
        ],
      ],
    );
  }
}

/// Connected device card — shown for any transport type.
class _ConnectedDeviceCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    IconData icon;
    switch (ble.connectionType) {
      case ConnectionType.tcp:
        icon = Icons.wifi;
        break;
      case ConnectionType.serial:
        icon = Icons.usb;
        break;
      default:
        icon = Icons.bluetooth_connected;
    }

    return Card(
      color: theme.colorScheme.primaryContainer,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Icon(icon, color: theme.colorScheme.onPrimaryContainer),
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
                  Row(
                    children: [
                      if (ble.connectionLabel.isNotEmpty)
                        Text(
                          '${ble.connectionType?.name.toUpperCase() ?? "BLE"}: ${ble.connectionLabel}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onPrimaryContainer
                                .withAlpha(150),
                          ),
                        ),
                      if (ble.deviceState.firmwareVersion != null) ...[
                        if (ble.connectionLabel.isNotEmpty)
                          Text(' · ',
                              style: theme.textTheme.bodySmall?.copyWith(
                                  color: theme.colorScheme.onPrimaryContainer
                                      .withAlpha(120))),
                        Text(
                          'FW: ${ble.deviceState.firmwareVersion}',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onPrimaryContainer
                                .withAlpha(150),
                          ),
                        ),
                      ],
                    ],
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
    );
  }
}

/// Bluetooth scan + pair tab.
class _BluetoothTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    return Column(
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
        const SizedBox(height: 12),

        // Discovered devices
        if (ble.discoveredDevices.isNotEmpty)
          ...ble.discoveredDevices.map((device) {
            final deviceId = device.device.remoteId.toString();
            final isThisConnecting =
                ble.isConnecting && ble.connectingDeviceId == deviceId;
            return ListTile(
              leading: const Icon(Icons.bluetooth),
              title: Text(device.name),
              subtitle: Text('RSSI: ${device.rssi} dBm'),
              trailing: isThisConnecting
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : OutlinedButton(
                      onPressed: ble.isConnecting
                          ? null
                          : () => ble.connectToDevice(device),
                      child: const Text('Pair'),
                    ),
            );
          })
        else
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
    );
  }
}

/// Network (TCP/WiFi) connection tab.
class _NetworkTab extends StatelessWidget {
  final TextEditingController ipController;
  final TextEditingController portController;

  const _NetworkTab({
    required this.ipController,
    required this.portController,
  });

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Connect to a Meshtastic device on your local network.',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurfaceVariant,
                  ),
            ),
            const SizedBox(height: 16),
            Row(
              children: [
                Expanded(
                  flex: 3,
                  child: TextField(
                    controller: ipController,
                    decoration: const InputDecoration(
                      labelText: 'IP Address',
                      hintText: '192.168.1.x',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  flex: 1,
                  child: TextField(
                    controller: portController,
                    decoration: const InputDecoration(
                      labelText: 'Port',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.number,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: ble.isConnecting
                    ? null
                    : () {
                        final ip = ipController.text.trim();
                        if (ip.isEmpty) return;
                        final port =
                            int.tryParse(portController.text.trim()) ?? 4403;
                        ble.connectViaTcp(ip, port: port);
                      },
                icon: const Icon(Icons.wifi),
                label: Text(ble.isConnecting ? 'Connecting...' : 'Connect'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// USB Serial (OTG) connection tab — Android only.
class _SerialTab extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final theme = Theme.of(context);

    return Column(
      children: [
        // Scan USB button
        SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () => ble.scanUsbDevices(),
            icon: const Icon(Icons.usb),
            label: const Text('Scan USB Devices'),
          ),
        ),
        const SizedBox(height: 12),

        if (ble.discoveredUsbDevices.isNotEmpty)
          ...ble.discoveredUsbDevices.map((usbDevice) {
            final label =
                usbDevice.productName ?? 'USB #${usbDevice.deviceId}';
            return ListTile(
              leading: const Icon(Icons.usb),
              title: Text(label),
              subtitle: Text(
                  'VID: ${usbDevice.vid}  PID: ${usbDevice.pid}'),
              trailing: OutlinedButton(
                onPressed: ble.isConnecting
                    ? null
                    : () => ble.connectViaSerial(usbDevice),
                child: Text(ble.isConnecting ? 'Connecting...' : 'Connect'),
              ),
            );
          })
        else
          SizedBox(
            width: double.infinity,
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'No USB devices found.\nConnect a Meshtastic device via USB OTG.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Settings card — profile, region, name, wi-fi
//
// Nothing is written to the device until the user taps Save.
// ═══════════════════════════════════════════════════════════════════════════════

/// Map the 4 admin profiles to the closest DeviceRole for initial selection.
MeshtasticProfile _profileFromDeviceRole(DeviceRole role) {
  switch (role) {
    case DeviceRole.tracker:
      return MeshtasticProfile.pilot;
    case DeviceRole.router:
    case DeviceRole.routerClient:
      return MeshtasticProfile.repeater;
    default:
      return MeshtasticProfile.driver;
  }
}

class _SettingsCard extends StatefulWidget {
  @override
  State<_SettingsCard> createState() => _SettingsCardState();
}

class _SettingsCardState extends State<_SettingsCard> {
  late MeshtasticProfile _selectedProfile;
  late RegionCode _region;
  late TextEditingController _longNameCtl;
  late TextEditingController _shortNameCtl;

  // Wi-Fi (Driver roles only)
  late TextEditingController _ssidCtl;
  late TextEditingController _pskCtl;
  bool _obscurePassword = true;
  bool _wifiScanning = false;
  List<WiFiAccessPoint> _networks = [];
  String? _wifiScanError;

  // Track what the device currently has so we know what changed.
  late MeshtasticProfile _deviceProfile;
  late RegionCode _deviceRegion;

  // Tracks whether we've already synced local fields from a completed
  // config load — prevents re-overwriting user edits on every rebuild
  // while still catching the first configLoaded transition.
  bool _configWasLoaded = false;

  @override
  void initState() {
    super.initState();
    final ds = context.read<BleService>().deviceState;
    _selectedProfile = _profileFromDeviceRole(ds.role);
    _deviceProfile = _selectedProfile;
    _region = ds.region;
    _deviceRegion = ds.region;
    _longNameCtl = TextEditingController(text: ds.longName);
    _shortNameCtl = TextEditingController(text: ds.shortName);
    _ssidCtl = TextEditingController(text: ds.wifiSsid);
    _pskCtl = TextEditingController(text: ds.wifiPsk);

    // If config is already loaded (e.g. navigated here after connect),
    // mark it so didChangeDependencies doesn't overwrite on first call.
    _configWasLoaded = context.read<BleService>().configLoaded;
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final ble = context.read<BleService>();
    // Re-sync local fields when config finishes loading for the first time
    if (ble.configLoaded && !_configWasLoaded) {
      _configWasLoaded = true;
      final ds = ble.deviceState;
      setState(() {
        _selectedProfile = _profileFromDeviceRole(ds.role);
        _deviceProfile = _selectedProfile;
        _region = ds.region;
        _deviceRegion = ds.region;
        _longNameCtl.text = ds.longName;
        _shortNameCtl.text = ds.shortName;
        _ssidCtl.text = ds.wifiSsid;
        _pskCtl.text = ds.wifiPsk;
      });
    }
    // Reset when device disconnects so next connect re-syncs
    if (!ble.configLoaded) {
      _configWasLoaded = false;
    }
  }

  @override
  void dispose() {
    _longNameCtl.dispose();
    _shortNameCtl.dispose();
    _ssidCtl.dispose();
    _pskCtl.dispose();
    super.dispose();
  }

  /// Wi-Fi section is shown only when the admin has enabled Wi-Fi for
  /// the currently selected profile on the backend.
  bool get _profileHasWifi =>
      ProfileConfig.presets[_selectedProfile]?.wifiEnabled ?? false;

  /// Save all pending changes to the device.
  ///
  /// Always pushes the full admin profile to the device so every
  /// setting (bluetooth, power, display, etc.) stays in sync with
  /// what the admin configured on the website. The device reboots
  /// after a commit.
  Future<void> _save() async {
    final ble = context.read<BleService>();

    // Region must be set before anything else.
    if (_region == RegionCode.unset) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.red,
          content: Text(
            'Set the LoRa Region first — your radio will not transmit '
            'on the right frequency until it is set.',
          ),
        ),
      );
      return;
    }

    final profileChanged = _selectedProfile != _deviceProfile;

    // Confirm before applying — the device will reboot.
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(profileChanged
            ? 'Apply ${_selectedProfile.label} profile?'
            : 'Save settings?'),
        content: Text(profileChanged
            ? 'This will overwrite all device settings with the '
              '${_selectedProfile.label} profile and reboot the device.'
            : 'This will sync all admin profile settings to the device '
              'and reboot it.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(profileChanged ? 'Apply & Reboot' : 'Save & Reboot'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    // 1. Push region first (updates _deviceState.region so applyProfile
    //    picks up the right value for the LoRa config write).
    final regionChanged = _region != _deviceRegion;
    if (regionChanged) {
      await ble.setLoraRegion(_region);
      _deviceRegion = _region;
    }

    // 2. Push device name.
    final longName = _longNameCtl.text.trim();
    final shortName = _shortNameCtl.text.trim();
    if (longName.isNotEmpty || shortName.isNotEmpty) {
      await ble.setDeviceName(longName: longName, shortName: shortName);
    }

    // 3. Push Wi-Fi credentials if the profile has Wi-Fi enabled.
    if (_profileHasWifi && _ssidCtl.text.trim().isNotEmpty) {
      await ble.setWifi(
        enabled: true,
        ssid: _ssidCtl.text.trim(),
        password: _pskCtl.text,
      );
    }

    // 4. Always push the full profile so every admin setting (bluetooth,
    //    power, display, modules, etc.) is written to the device.
    await ble.applyProfile(_selectedProfile);
    _deviceProfile = _selectedProfile;

    if (mounted) setState(() {});
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

    // While the BLE config dump is still in progress, show a loading
    // indicator instead of the form — prevents the false "Region not
    // set" banner that fires when device defaults are still unset.
    if (!ble.configLoaded) {
      return Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              const SizedBox(width: 12),
              Text('Reading device settings…',
                  style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      );
    }

    final disabled = ble.isPushingConfig;
    final regionUnset = _region == RegionCode.unset;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (regionUnset) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.12),
                  border: Border.all(color: Colors.red, width: 1.5),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    const Icon(Icons.warning_amber_rounded, color: Colors.red),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'LoRa Region is not set. The radio will NOT '
                        'transmit on the right frequency until you pick '
                        'a region below.',
                        style: TextStyle(
                          color: Colors.red[900],
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
            ],

            // ── Profile ──
            Text('Profile', style: theme.textTheme.labelMedium?.copyWith(
              fontWeight: FontWeight.bold,
            )),
            const SizedBox(height: 8),
            InputDecorator(
              decoration: const InputDecoration(
                border: OutlineInputBorder(),
                contentPadding:
                    EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              ),
              child: DropdownButtonHideUnderline(
                child: DropdownButton<MeshtasticProfile>(
                  value: _selectedProfile,
                  isExpanded: true,
                  onChanged: disabled
                      ? null
                      : (v) {
                          if (v != null) setState(() => _selectedProfile = v);
                        },
                  items: MeshtasticProfile.values
                      .map((p) => DropdownMenuItem(
                            value: p,
                            child: Text(p.label),
                          ))
                      .toList(),
                ),
              ),
            ),
            const SizedBox(height: 4),
            Text(
              _profileDescription(_selectedProfile),
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurfaceVariant,
              ),
            ),

            const Divider(height: 32),

            // ── Region ──
            // Region is REQUIRED. Placed early so it's set before anything else.
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                border: Border.all(
                  color: regionUnset
                      ? Colors.red
                      : theme.colorScheme.outlineVariant,
                  width: regionUnset ? 1.5 : 1,
                ),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      'Region *',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: regionUnset ? Colors.red : null,
                        fontWeight: regionUnset ? FontWeight.w600 : null,
                      ),
                    ),
                  ),
                  DropdownButtonHideUnderline(
                    child: DropdownButton<RegionCode>(
                      value: _region,
                      iconEnabledColor: regionUnset ? Colors.red : null,
                      onChanged: disabled
                          ? null
                          : (v) {
                              if (v != null) setState(() => _region = v);
                            },
                      items: RegionCode.values
                          .map((r) => DropdownMenuItem(
                                value: r,
                                child: Text(
                                  r.label,
                                  style: TextStyle(
                                    color: r == RegionCode.unset
                                        ? Colors.red
                                        : null,
                                  ),
                                ),
                              ))
                          .toList(),
                    ),
                  ),
                ],
              ),
            ),
            if (regionUnset) ...[
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.only(left: 12),
                child: Text(
                  'Required. Pick the regulatory zone for where the '
                  'device will operate.',
                  style: TextStyle(color: Colors.red[800], fontSize: 12),
                ),
              ),
            ],

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

            // ── Wi-Fi (only when admin has wifi_enabled for this profile) ──
            if (_profileHasWifi) ...[
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
            ],

            const Divider(height: 32),

            // ── Save button ──
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: disabled ? null : _save,
                icon: const Icon(Icons.save, size: 18),
                label: const Text('Save'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static String _profileDescription(MeshtasticProfile p) {
    switch (p) {
      case MeshtasticProfile.pilot:
        return 'Optimised for position tracking (pilots in the air)';
      case MeshtasticProfile.driver:
        return 'Ground support relay via Bluetooth mesh';
      case MeshtasticProfile.driverWifi:
        return 'Ground support relay via Bluetooth + Wi-Fi uplink';
      case MeshtasticProfile.repeater:
        return 'Always-on relay / base station for mesh coverage';
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Device Settings card — collapsible, read-only profile values
//
// Shows all fields that match the admin web page, organised by category.
// Collapsed by default to keep the screen clean.
// ═══════════════════════════════════════════════════════════════════════════════

class _DeviceSettingsCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();
    final ds = ble.deviceState;
    final theme = Theme.of(context);

    final broker =
        ds.mqttAddress.isNotEmpty ? ds.mqttAddress : 'mqtt.meshtastic.org';

    return Card(
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        title: Text(
          'Device Settings',
          style: theme.textTheme.titleSmall?.copyWith(
            color: theme.colorScheme.primary,
          ),
        ),
        subtitle: Text(
          'Current device configuration (read-only)',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
        leading: Icon(Icons.settings, color: theme.colorScheme.primary),
        initiallyExpanded: false,
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          // ── Device ──
          _GroupHeader(label: 'Device', theme: theme),
          _ConfigRow(label: 'Role', value: ds.role.label, theme: theme),
          _ConfigRow(
              label: 'Rebroadcast',
              value: ds.rebroadcastMode.label,
              theme: theme),

          const Divider(height: 24),

          // ── Position ──
          _GroupHeader(label: 'Position', theme: theme),
          _ConfigRow(
              label: 'GPS mode', value: ds.gpsMode.label, theme: theme),
          _ConfigRow(
              label: 'Broadcast interval',
              value: '${ds.positionBroadcastSecs}s',
              theme: theme),
          _ConfigRow(
              label: 'Smart position',
              value: ds.smartPositionEnabled ? 'Yes' : 'No',
              theme: theme),
          if (ds.smartPositionEnabled) ...[
            _ConfigRow(
                label: '  Min distance',
                value: '${ds.smartMinDistance} m',
                theme: theme),
            _ConfigRow(
                label: '  Min interval',
                value: '${ds.smartMinInterval}s',
                theme: theme),
          ],
          _ConfigRow(
              label: 'Position flags',
              value: _positionFlagsLabel(ds.positionFlags),
              theme: theme),

          const Divider(height: 24),

          // ── LoRa ──
          _GroupHeader(label: 'LoRa', theme: theme),
          _ConfigRow(
              label: 'Region', value: ds.region.label, theme: theme),
          _ConfigRow(
              label: 'Modem preset',
              value: ds.modemPreset.label,
              theme: theme),
          _ConfigRow(
              label: 'Hop limit', value: '${ds.hopLimit}', theme: theme),
          _ConfigRow(
              label: 'TX enabled',
              value: ds.txEnabled ? 'Yes' : 'No',
              theme: theme),

          const Divider(height: 24),

          // ── Power ──
          _GroupHeader(label: 'Power', theme: theme),
          _ConfigRow(
              label: 'Power saving',
              value: ds.isPowerSaving ? 'Yes' : 'No',
              theme: theme),

          const Divider(height: 24),

          // ── Bluetooth ──
          _GroupHeader(label: 'Bluetooth', theme: theme),
          _ConfigRow(
              label: 'Bluetooth',
              value: ds.bluetoothEnabled ? 'On' : 'Off',
              theme: theme),
          _ConfigRow(
              label: 'Pairing mode',
              value: ds.blePairingMode.label,
              theme: theme),

          const Divider(height: 24),

          // ── Network ──
          _GroupHeader(label: 'Network', theme: theme),
          _ConfigRow(
              label: 'Wi-Fi',
              value: ds.wifiEnabled ? 'On' : 'Off',
              theme: theme),
          if (ds.wifiEnabled && ds.wifiSsid.isNotEmpty)
            _ConfigRow(
                label: '  SSID', value: ds.wifiSsid, theme: theme),

          const Divider(height: 24),

          // ── Display ──
          _GroupHeader(label: 'Display', theme: theme),
          _ConfigRow(
              label: 'Display timeout',
              value: ds.screenOnSecs == 0
                  ? 'Always on'
                  : '${ds.screenOnSecs}s',
              theme: theme),

          const Divider(height: 24),

          // ── MQTT ──
          _GroupHeader(label: 'MQTT', theme: theme),
          _ConfigRow(
              label: 'MQTT enabled',
              value: ds.mqttEnabled ? 'Yes' : 'No',
              theme: theme),
          if (ds.mqttEnabled) ...[
            _ConfigRow(label: 'Broker', value: broker, theme: theme),
            _ConfigRow(
                label: 'Topic prefix',
                value:
                    ds.mqttRootTopic.isNotEmpty ? ds.mqttRootTopic : 'msh',
                theme: theme),
          ],

          const Divider(height: 24),

          // ── Modules ──
          _GroupHeader(label: 'Modules', theme: theme),
          _ConfigRow(
              label: 'Telemetry interval',
              value: _formatHours(ds.telemetryDeviceInterval),
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

  static String _formatHours(int seconds) {
    if (seconds <= 0) return '0';
    final hours = seconds / 3600;
    if (hours == hours.truncateToDouble()) {
      return '${hours.toInt()}h';
    }
    return '${hours.toStringAsFixed(1)}h';
  }

  static String _positionFlagsLabel(int flags) {
    if (flags == 0) return 'None';
    final parts = <String>[];
    if (flags & PositionFlags.altitude != 0) parts.add('Alt');
    if (flags & PositionFlags.altitudeMsl != 0) parts.add('MSL');
    if (flags & PositionFlags.geoidalSeparation != 0) parts.add('Geoid');
    if (flags & PositionFlags.dop != 0) parts.add('DOP');
    if (flags & PositionFlags.hvdop != 0) parts.add('HVDOP');
    if (flags & PositionFlags.satInView != 0) parts.add('Sats');
    if (flags & PositionFlags.seqNo != 0) parts.add('Seq');
    if (flags & PositionFlags.timestamp != 0) parts.add('Time');
    if (flags & PositionFlags.heading != 0) parts.add('Hdg');
    if (flags & PositionFlags.speed != 0) parts.add('Spd');
    return parts.join(', ');
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════════════════

class _GroupHeader extends StatelessWidget {
  final String label;
  final ThemeData theme;

  const _GroupHeader({required this.label, required this.theme});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        label.toUpperCase(),
        style: theme.textTheme.labelSmall?.copyWith(
          fontWeight: FontWeight.w700,
          letterSpacing: 0.8,
          color: theme.colorScheme.primary,
        ),
      ),
    );
  }
}

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
          Flexible(
            child: Text(label, style: theme.textTheme.bodyMedium),
          ),
          const SizedBox(width: 16),
          Text(value,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.w600,
              )),
        ],
      ),
    );
  }
}
