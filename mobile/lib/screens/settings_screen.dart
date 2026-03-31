import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/auth_service.dart';
import '../services/ble_service.dart';
import '../services/tracking_service.dart';
import 'meshtastic_settings_screen.dart';

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

          // ── Meshtastic ──
          Text('Meshtastic',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),
          Card(
            child: InkWell(
              borderRadius: BorderRadius.circular(12),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => const MeshtasticSettingsScreen(),
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  children: [
                    Icon(
                      ble.isConnected
                          ? Icons.bluetooth_connected
                          : Icons.bluetooth,
                      color: ble.isConnected
                          ? Colors.green
                          : theme.colorScheme.primary,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Meshtastic Device Settings',
                            style: theme.textTheme.titleSmall,
                          ),
                          const SizedBox(height: 2),
                          Text(
                            ble.isConnected
                                ? 'Connected: ${ble.deviceDisplayName}'
                                : 'Scan, connect, and configure',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right,
                        color: theme.colorScheme.onSurfaceVariant),
                  ],
                ),
              ),
            ),
          ),

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

          // ── Flight Settings ──
          Text('Flight Settings',
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
                  // Sport type selector
                  Row(
                    children: [
                      Icon(Icons.paragliding,
                          size: 20, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Sport type',
                          style: theme.textTheme.bodyMedium,
                        ),
                      ),
                      DropdownButton<SportType>(
                        value: tracking.sportType,
                        onChanged: (value) {
                          if (value != null) tracking.setSportType(value);
                        },
                        items: const [
                          DropdownMenuItem(
                            value: SportType.paraglider,
                            child: Text('Paraglider'),
                          ),
                          DropdownMenuItem(
                            value: SportType.hangGlider,
                            child: Text('Hang Glider'),
                          ),
                          DropdownMenuItem(
                            value: SportType.glider,
                            child: Text('Glider'),
                          ),
                        ],
                      ),
                    ],
                  ),
                  const Divider(height: 24),
                  // Multi-flight toggle
                  Row(
                    children: [
                      Icon(Icons.replay,
                          size: 20, color: theme.colorScheme.primary),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              'Multi-flight tracking',
                              style: theme.textTheme.bodyMedium,
                            ),
                            Text(
                              'Monitor for re-launch after landing',
                              style: theme.textTheme.bodySmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                          ],
                        ),
                      ),
                      Switch(
                        value: tracking.multiFlightEnabled,
                        onChanged: (enabled) {
                          tracking.setMultiFlightEnabled(enabled);
                        },
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(height: 32),

          // ── Units Section ──
          Text('Units',
              style: theme.textTheme.titleSmall?.copyWith(
                color: theme.colorScheme.primary,
              )),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  _UnitRow(
                    icon: Icons.height,
                    label: 'Altitude',
                    value: user?.altitudeUnit ?? 'ft',
                    options: const {'m': 'Metres', 'ft': 'Feet'},
                    onChanged: (v) => auth.updateUnit(altitudeUnit: v),
                  ),
                  const Divider(height: 20),
                  _UnitRow(
                    icon: Icons.speed,
                    label: 'Speed',
                    value: user?.speedUnit ?? 'kph',
                    options: const {
                      'kph': 'km/h',
                      'mph': 'mph',
                      'kts': 'Knots',
                    },
                    onChanged: (v) => auth.updateUnit(speedUnit: v),
                  ),
                  const Divider(height: 20),
                  _UnitRow(
                    icon: Icons.straighten,
                    label: 'Distance',
                    value: user?.distanceUnit ?? 'km',
                    options: const {'km': 'Kilometres', 'mi': 'Miles'},
                    onChanged: (v) => auth.updateUnit(distanceUnit: v),
                  ),
                  const Divider(height: 20),
                  _UnitRow(
                    icon: Icons.trending_up,
                    label: 'Vario',
                    value: user?.varioUnit ?? 'fpm',
                    options: const {'ms': 'm/s', 'fpm': 'ft/min'},
                    onChanged: (v) => auth.updateUnit(varioUnit: v),
                  ),
                ],
              ),
            ),
          ),

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

class _UnitRow extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Map<String, String> options;
  final ValueChanged<String> onChanged;

  const _UnitRow({
    required this.icon,
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Icon(icon, size: 20, color: theme.colorScheme.primary),
        const SizedBox(width: 8),
        Expanded(
          child: Text(label, style: theme.textTheme.bodyMedium),
        ),
        DropdownButton<String>(
          value: value,
          onChanged: (v) {
            if (v != null) onChanged(v);
          },
          items: options.entries
              .map((e) => DropdownMenuItem(
                    value: e.key,
                    child: Text(e.value),
                  ))
              .toList(),
        ),
      ],
    );
  }
}
