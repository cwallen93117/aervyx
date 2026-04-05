import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/ble_service.dart';
import 'meshtastic_settings_screen.dart';

class BlePairingScreen extends StatelessWidget {
  const BlePairingScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ble = context.watch<BleService>();

    return Scaffold(
      appBar: AppBar(title: const Text('Meshtastic BLE')),
      body: SafeArea(
        child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Scan controls
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: ble.isScanning ? null : () => ble.startScan(),
                    icon: const Icon(Icons.bluetooth_searching),
                    label: Text(ble.isScanning ? 'Scanning...' : 'Scan for Devices'),
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
              Text(ble.error!, style: const TextStyle(color: Colors.red)),
            ],

            if (ble.statusMessage != null) ...[
              const SizedBox(height: 12),
              Text(ble.statusMessage!,
                  style: const TextStyle(color: Colors.green)),
            ],

            const SizedBox(height: 16),

            // Connected device section
            if (ble.connectedDevice != null) ...[
              Card(
                color: Colors.green.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Connected: ${ble.deviceDisplayName}',
                          style: Theme.of(context).textTheme.titleSmall),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          FilledButton.icon(
                            onPressed: () => Navigator.of(context).push(
                              MaterialPageRoute(
                                builder: (_) =>
                                    const MeshtasticSettingsScreen(),
                              ),
                            ),
                            icon: const Icon(Icons.settings),
                            label: const Text('Configure'),
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
              const SizedBox(height: 16),
            ],

            // Discovered devices list
            Text('Discovered Devices',
                style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),

            Expanded(
              child: ble.discoveredDevices.isEmpty
                  ? const Center(
                      child: Text('No Meshtastic devices found.\nTap Scan to search.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.grey)),
                    )
                  : ListView.builder(
                      itemCount: ble.discoveredDevices.length,
                      itemBuilder: (context, index) {
                        final device = ble.discoveredDevices[index];
                        final isConnected =
                            ble.connectedDevice?.device.remoteId ==
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
                      },
                    ),
            ),
          ],
        ),
      ),
      ),
    );
  }
}
