import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/tracking_service.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();
    final ble = context.watch<BleService>();
    final tracking = context.watch<TrackingService>();
    final theme = Theme.of(context);
    final user = auth.user;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── User Info ──
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 24,
                    child: Text(
                      user != null
                          ? user.fullName
                              .split(' ')
                              .map((w) => w.isNotEmpty ? w[0] : '')
                              .take(2)
                              .join()
                              .toUpperCase()
                          : '?',
                      style: const TextStyle(fontSize: 18),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          user?.fullName ?? 'Unknown',
                          style: theme.textTheme.titleMedium,
                        ),
                        const SizedBox(height: 2),
                        Text(
                          user?.role.toUpperCase() ?? '',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 24),

          // ── Meshtastic BLE Section ──
          Text('Meshtastic BLE',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),

          // Scan controls
          Row(
            children: [
              Expanded(
                child: FilledButton.icon(
                  onPressed: ble.isScanning ? null : () => ble.startScan(),
                  icon: const Icon(Icons.bluetooth_searching),
                  label: Text(
                      ble.isScanning ? 'Scanning...' : 'Scan for Devices'),
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
            Text(ble.statusMessage!,
                style: const TextStyle(color: Colors.green)),
          ],

          const SizedBox(height: 12),

          // Connected device card
          if (ble.connectedDevice != null) ...[
            Card(
              color: theme.colorScheme.primaryContainer,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(Icons.bluetooth_connected,
                            color: theme.colorScheme.onPrimaryContainer),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Connected: ${ble.connectedDevice!.name}',
                            style: theme.textTheme.titleSmall?.copyWith(
                              color: theme.colorScheme.onPrimaryContainer,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        FilledButton.icon(
                          onPressed: ble.isPushingConfig
                              ? null
                              : () => ble.pushConfiguration(),
                          icon: const Icon(Icons.upload),
                          label: Text(ble.isPushingConfig
                              ? 'Pushing...'
                              : 'Push Config'),
                        ),
                        const SizedBox(width: 12),
                        OutlinedButton(
                          onPressed: () => ble.disconnect(),
                          child: const Text('Disconnect'),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 12),
          ],

          // Discovered devices list
          if (ble.discoveredDevices.isNotEmpty) ...[
            Text('Discovered Devices',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurfaceVariant,
                )),
            const SizedBox(height: 4),
            ...ble.discoveredDevices.map((device) {
              final isConnected = ble.connectedDevice?.device.remoteId ==
                  device.device.remoteId;
              return ListTile(
                leading: Icon(
                  Icons.bluetooth,
                  color: isConnected ? Colors.green : null,
                ),
                title: Text(device.name),
                subtitle: Text('RSSI: ${device.rssi} dBm'),
                trailing: isConnected
                    ? const Chip(label: Text('Connected'))
                    : OutlinedButton(
                        onPressed: ble.isConnecting
                            ? null
                            : () => ble.connectToDevice(device),
                        child: const Text('Pair'),
                      ),
              );
            }),
          ] else ...[
            Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  'No Meshtastic devices found.\nTap Scan to search.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
            ),
          ],

          const SizedBox(height: 32),

          // ── Battery Threshold ──
          Text('Battery Protection',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(Icons.battery_saver,
                          size: 20, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Auto-stop tracking when battery is low',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                      Switch(
                        value: tracking.batteryThreshold != null,
                        onChanged: (enabled) {
                          tracking.setBatteryThreshold(enabled ? 15 : null);
                        },
                      ),
                    ],
                  ),
                  if (tracking.batteryThreshold != null) ...[
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        Text('Stop at:',
                            style: theme.textTheme.bodySmall),
                        Expanded(
                          child: Slider(
                            value: tracking.batteryThreshold!.toDouble(),
                            min: 5,
                            max: 50,
                            divisions: 9,
                            label: '${tracking.batteryThreshold}%',
                            onChanged: (value) {
                              tracking.setBatteryThreshold(value.round());
                            },
                          ),
                        ),
                        SizedBox(
                          width: 42,
                          child: Text(
                            '${tracking.batteryThreshold}%',
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    if (tracking.currentBatteryLevel != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(
                          'Current battery: ${tracking.currentBatteryLevel}%',
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ),
                  ],
                ],
              ),
            ),
          ),

          const SizedBox(height: 32),

          // ── SOS Message ──
          Text('SOS Message',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),
          _SosMessageEditor(ble: ble),

          const SizedBox(height: 32),

          // ── App Info ──
          Text('App Info',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  _InfoRow(label: 'App', value: 'Aervyx Pilot'),
                  const SizedBox(height: 4),
                  _InfoRow(label: 'Version', value: '0.1.0'),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SosMessageEditor extends StatefulWidget {
  final BleService ble;

  const _SosMessageEditor({required this.ble});

  @override
  State<_SosMessageEditor> createState() => _SosMessageEditorState();
}

class _SosMessageEditorState extends State<_SosMessageEditor> {
  late final TextEditingController _controller;
  bool _dirty = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.ble.sosMessage);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _save() {
    final text = _controller.text.trim();
    if (text.isNotEmpty) {
      widget.ble.setSosMessage(text);
      setState(() => _dirty = false);
      FocusScope.of(context).unfocus();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('SOS message saved'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.sos, size: 20, color: Colors.red),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Message broadcast on all mesh nodes and over cellular when SOS is triggered',
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _controller,
              maxLines: 1,
              textInputAction: TextInputAction.done,
              onChanged: (_) {
                if (!_dirty) setState(() => _dirty = true);
              },
              onSubmitted: (_) => _save(),
              decoration: InputDecoration(
                border: const OutlineInputBorder(),
                hintText: 'Enter your SOS message...',
                suffixIcon: _dirty
                    ? IconButton(
                        icon: const Icon(Icons.check_circle, color: Colors.green),
                        tooltip: 'Save',
                        onPressed: _save,
                      )
                    : const Icon(Icons.check, color: Colors.grey),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;

  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: Theme.of(context).textTheme.bodyMedium),
        Text(value, style: Theme.of(context).textTheme.bodySmall),
      ],
    );
  }
}
