import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/auth_service.dart';
import '../services/driver_service.dart';

/// Home screen for driver-profile users.
///
/// Shows a map with assigned pilot positions and a "Navigate" button
/// that opens Google Maps with turn-by-turn directions.
class DriverHomeScreen extends StatefulWidget {
  const DriverHomeScreen({super.key});

  @override
  State<DriverHomeScreen> createState() => _DriverHomeScreenState();
}

class _DriverHomeScreenState extends State<DriverHomeScreen> {
  DriverPilot? _selectedPilot;

  @override
  void initState() {
    super.initState();
    // Connect to live stream
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DriverService>().connect();
    });
  }

  /// Open Google Maps navigation to the pilot's position.
  Future<void> _navigateToPilot(DriverPilot pilot) async {
    final uri = Uri.parse(
      'google.navigation:q=${pilot.lat},${pilot.lon}&mode=d',
    );

    // Try Google Maps first, fall back to generic geo: URI
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
    } else {
      final geoUri = Uri.parse(
        'geo:${pilot.lat},${pilot.lon}?q=${pilot.lat},${pilot.lon}',
      );
      if (await canLaunchUrl(geoUri)) {
        await launchUrl(geoUri);
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('No navigation app found')),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final driver = context.watch<DriverService>();
    final auth = context.watch<AuthService>();
    final theme = Theme.of(context);
    final pilots = driver.visiblePilots;

    return Scaffold(
      appBar: AppBar(
        title: Text(driver.taskName ?? 'Driver View'),
        actions: [
          // Toggle my pilots / all pilots
          IconButton(
            icon: Icon(
              driver.showAllPilots ? Icons.people : Icons.person,
            ),
            tooltip: driver.showAllPilots ? 'Show my pilots' : 'Show all pilots',
            onPressed: driver.toggleShowAllPilots,
          ),
          // Connection indicator
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Icon(
              Icons.circle,
              size: 12,
              color: driver.connected ? Colors.green : Colors.red,
            ),
          ),
          // Logout
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Logout',
            onPressed: () {
              driver.disconnect();
              auth.logout();
            },
          ),
        ],
      ),
      body: driver.error != null && pilots.isEmpty
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(32),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.cloud_off,
                        size: 48, color: theme.colorScheme.error),
                    const SizedBox(height: 16),
                    Text(driver.error!,
                        style: theme.textTheme.bodyMedium,
                        textAlign: TextAlign.center),
                    const SizedBox(height: 16),
                    FilledButton(
                      onPressed: () => driver.connect(),
                      child: const Text('Retry'),
                    ),
                  ],
                ),
              ),
            )
          : Column(
              children: [
                // Map
                Expanded(
                  flex: 3,
                  child: FlutterMap(
                    options: MapOptions(
                      initialCenter: pilots.isNotEmpty
                          ? LatLng(pilots.first.lat, pilots.first.lon)
                          : const LatLng(46.0, 11.0),
                      initialZoom: 12,
                      onTap: (_, __) {
                        setState(() => _selectedPilot = null);
                      },
                    ),
                    children: [
                      TileLayer(
                        urlTemplate:
                            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.aervyx.aervyx_mobile',
                      ),
                      MarkerLayer(
                        markers: pilots.map((pilot) {
                          final isSelected =
                              _selectedPilot?.pilotId == pilot.pilotId;
                          return Marker(
                            point: LatLng(pilot.lat, pilot.lon),
                            width: 44,
                            height: 50,
                            child: GestureDetector(
                              onTap: () =>
                                  setState(() => _selectedPilot = pilot),
                              child: _DriverPilotMarker(
                                pilot: pilot,
                                isSelected: isSelected,
                              ),
                            ),
                          );
                        }).toList(),
                      ),
                    ],
                  ),
                ),

                // Pilot list
                Expanded(
                  flex: 2,
                  child: pilots.isEmpty
                      ? Center(
                          child: Text(
                            'No pilots in view',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                        )
                      : ListView.builder(
                          itemCount: pilots.length,
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          itemBuilder: (context, index) {
                            final pilot = pilots[index];
                            final isSelected =
                                _selectedPilot?.pilotId == pilot.pilotId;

                            return _DriverPilotCard(
                              pilot: pilot,
                              isSelected: isSelected,
                              onTap: () =>
                                  setState(() => _selectedPilot = pilot),
                              onNavigate: () => _navigateToPilot(pilot),
                            );
                          },
                        ),
                ),
              ],
            ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pilot map marker for driver view
// ═══════════════════════════════════════════════════════════════════════════════

class _DriverPilotMarker extends StatelessWidget {
  final DriverPilot pilot;
  final bool isSelected;

  const _DriverPilotMarker({required this.pilot, required this.isSelected});

  @override
  Widget build(BuildContext context) {
    final color = pilot.assigned ? Colors.blue : Colors.grey;
    final borderColor = isSelected ? Colors.orange : color;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.all(4),
          decoration: BoxDecoration(
            color: Colors.white,
            shape: BoxShape.circle,
            border: Border.all(color: borderColor, width: isSelected ? 3 : 2),
            boxShadow: [
              BoxShadow(color: Colors.black.withAlpha(40), blurRadius: 3),
            ],
          ),
          child: Icon(
            Icons.paragliding,
            size: 18,
            color: color,
          ),
        ),
        Text(
          pilot.compNumber != null ? '#${pilot.compNumber}' : pilot.name,
          style: TextStyle(
            fontSize: 9,
            fontWeight: FontWeight.bold,
            color: isSelected ? Colors.orange.shade800 : Colors.black87,
          ),
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Pilot card in the driver list
// ═══════════════════════════════════════════════════════════════════════════════

class _DriverPilotCard extends StatelessWidget {
  final DriverPilot pilot;
  final bool isSelected;
  final VoidCallback onTap;
  final VoidCallback onNavigate;

  const _DriverPilotCard({
    required this.pilot,
    required this.isSelected,
    required this.onTap,
    required this.onNavigate,
  });

  String _timeSinceUpdate() {
    final ago = DateTime.now().difference(pilot.lastSeen);
    if (ago.inSeconds < 10) return 'now';
    if (ago.inSeconds < 60) return '${ago.inSeconds}s ago';
    if (ago.inMinutes < 60) return '${ago.inMinutes}m ago';
    return '${ago.inHours}h ago';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
      color: isSelected
          ? theme.colorScheme.primaryContainer.withAlpha(120)
          : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          child: Row(
            children: [
              // Pilot info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        if (pilot.assigned)
                          Padding(
                            padding: const EdgeInsets.only(right: 6),
                            child: Icon(Icons.star,
                                size: 14, color: Colors.amber.shade700),
                          ),
                        Text(
                          pilot.compNumber != null
                              ? '#${pilot.compNumber} — ${pilot.name}'
                              : pilot.name,
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 2),
                    Row(
                      children: [
                        if (pilot.alt != null) ...[
                          Text(
                            '${pilot.alt!.toStringAsFixed(0)} m',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(width: 10),
                        ],
                        if (pilot.speed != null) ...[
                          Text(
                            '${(pilot.speed! * 3.6).toStringAsFixed(0)} km/h',
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: theme.colorScheme.onSurfaceVariant,
                            ),
                          ),
                          const SizedBox(width: 10),
                        ],
                        Text(
                          _timeSinceUpdate(),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
              // Navigate button
              FilledButton.icon(
                icon: const Icon(Icons.navigation, size: 18),
                label: const Text('Navigate'),
                onPressed: onNavigate,
                style: FilledButton.styleFrom(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  textStyle: const TextStyle(fontSize: 13),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
