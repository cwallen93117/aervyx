import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../models/driver_route.dart';
import '../services/routing_service.dart';
import '../widgets/map_scale_bar.dart';
import '../widgets/route_stop_card.dart';

/// Full-screen turn-by-turn navigation screen for drivers.
class DriverNavigationScreen extends StatefulWidget {
  final int taskId;

  const DriverNavigationScreen({super.key, required this.taskId});

  @override
  State<DriverNavigationScreen> createState() => _DriverNavigationScreenState();
}

class _DriverNavigationScreenState extends State<DriverNavigationScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final routing = context.read<RoutingService>();
      routing.fetchRoute(widget.taskId).then((_) {
        routing.startNavigation(widget.taskId);
      });
    });
  }

  @override
  void dispose() {
    // Don't stop navigation on dispose — let the service keep running
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final routing = context.watch<RoutingService>();
    final theme = Theme.of(context);
    final route = routing.route;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          route != null
              ? 'Route to ${route.stops.length} pilot${route.stops.length == 1 ? '' : 's'}'
              : 'Loading route...',
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'Re-optimize',
            onPressed: routing.loading ? null : () => routing.reoptimize(),
          ),
        ],
      ),
      body: routing.loading
          ? const Center(child: CircularProgressIndicator())
          : routing.error != null && route == null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline,
                            size: 48, color: theme.colorScheme.error),
                        const SizedBox(height: 16),
                        Text(routing.error!,
                            style: theme.textTheme.bodyMedium,
                            textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton(
                          onPressed: () => routing.fetchRoute(widget.taskId),
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                )
              : route == null
                  ? const Center(child: Text('No route available'))
                  : _buildRouteView(context, routing, route),
    );
  }

  Widget _buildRouteView(
    BuildContext context,
    RoutingService routing,
    DriverRoute route,
  ) {
    final theme = Theme.of(context);

    // Build polyline points from all legs
    final polylinePoints = <LatLng>[];
    for (final leg in route.legs) {
      polylinePoints.addAll(leg.shape);
    }
    // Fallback: if no shape, connect stops directly
    if (polylinePoints.isEmpty) {
      for (final stop in route.stops) {
        polylinePoints.add(LatLng(stop.lat, stop.lon));
      }
    }

    return Column(
      children: [
        // Map
        Expanded(
          flex: 3,
          child: FlutterMap(
            options: MapOptions(
              initialCenter: route.stops.isNotEmpty
                  ? LatLng(route.stops.first.lat, route.stops.first.lon)
                  : const LatLng(46.0, 11.0),
              initialZoom: 12,
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.aervyx.aervyx_mobile',
              ),
              // Route polyline
              if (polylinePoints.length >= 2)
                PolylineLayer(
                  polylines: [
                    Polyline(
                      points: polylinePoints,
                      color: Colors.blue.shade700,
                      strokeWidth: 4,
                    ),
                  ],
                ),
              // Stop markers
              MarkerLayer(
                markers: route.stops.asMap().entries.map((entry) {
                  final idx = entry.key;
                  final stop = entry.value;
                  final isCurrent = idx == routing.currentLegIndex;
                  return Marker(
                    point: LatLng(stop.lat, stop.lon),
                    width: 36,
                    height: 44,
                    child: _StopMarker(
                      index: idx + 1,
                      status: stop.status,
                      isCurrent: isCurrent,
                    ),
                  );
                }).toList(),
              ),
              const AppMapScaleBar(),
            ],
          ),
        ),

        // Current maneuver banner
        if (routing.currentManeuver != null)
          Container(
            width: double.infinity,
            color: theme.colorScheme.primaryContainer,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            child: Row(
              children: [
                Icon(
                  _maneuverIcon(routing.currentManeuver!.type),
                  size: 24,
                  color: theme.colorScheme.onPrimaryContainer,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    routing.currentManeuver!.instruction,
                    style: theme.textTheme.titleSmall?.copyWith(
                      color: theme.colorScheme.onPrimaryContainer,
                      fontWeight: FontWeight.w600,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  _formatDistance(routing.currentManeuver!.distanceKm),
                  style: theme.textTheme.titleSmall?.copyWith(
                    color: theme.colorScheme.onPrimaryContainer,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ],
            ),
          ),

        // Stop list + actions
        Expanded(
          flex: 2,
          child: Column(
            children: [
              // Summary bar
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                color: theme.colorScheme.surfaceContainerHighest,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '${route.totalDistanceKm.toStringAsFixed(1)} km',
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      route.totalTimeFormatted,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      '${route.stops.where((s) => s.status != "picked_up").length} remaining',
                      style: theme.textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              // Stop cards
              Expanded(
                child: ListView.builder(
                  itemCount: route.stops.length,
                  padding: EdgeInsets.only(
                    top: 4,
                    bottom: 4 + MediaQuery.of(context).padding.bottom,
                  ),
                  itemBuilder: (context, index) {
                    final stop = route.stops[index];
                    final isCurrent = index == routing.currentLegIndex;
                    return RouteStopCard(
                      stop: stop,
                      index: index + 1,
                      isCurrent: isCurrent,
                      onPickUp: isCurrent && stop.status != 'picked_up'
                          ? () => routing.markPickedUp(stop.landingId)
                          : null,
                      onSkip: isCurrent && stop.status != 'picked_up'
                          ? () => routing.skipCurrentStop()
                          : null,
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  String _formatDistance(double km) {
    if (km < 1) return '${(km * 1000).toInt()} m';
    return '${km.toStringAsFixed(1)} km';
  }

  IconData _maneuverIcon(int type) {
    // Valhalla maneuver type codes
    switch (type) {
      case 1:
        return Icons.arrow_upward; // straight
      case 2:
        return Icons.turn_slight_right; // slight right
      case 3:
        return Icons.turn_right; // right
      case 4:
        return Icons.turn_sharp_right_outlined; // sharp right
      case 5:
        return Icons.u_turn_right; // u-turn right
      case 6:
        return Icons.turn_sharp_left_outlined; // sharp left
      case 7:
        return Icons.turn_left; // left
      case 8:
        return Icons.turn_slight_left; // slight left
      case 9:
        return Icons.u_turn_left; // u-turn left
      case 10:
        return Icons.roundabout_right; // roundabout
      case 24:
        return Icons.flag; // arrive
      default:
        return Icons.arrow_forward;
    }
  }
}

/// Numbered stop marker for the map.
class _StopMarker extends StatelessWidget {
  final int index;
  final String status;
  final bool isCurrent;

  const _StopMarker({
    required this.index,
    required this.status,
    required this.isCurrent,
  });

  Color get _color {
    switch (status) {
      case 'picked_up':
        return Colors.blue;
      case 'ready':
        return Colors.green;
      case 'landed':
      default:
        return Colors.grey;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 28,
          height: 28,
          decoration: BoxDecoration(
            color: _color,
            shape: BoxShape.circle,
            border: Border.all(
              color: isCurrent ? Colors.orange : Colors.white,
              width: isCurrent ? 3 : 2,
            ),
            boxShadow: [
              BoxShadow(color: Colors.black.withAlpha(60), blurRadius: 4),
            ],
          ),
          child: Center(
            child: Text(
              '$index',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 12,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
