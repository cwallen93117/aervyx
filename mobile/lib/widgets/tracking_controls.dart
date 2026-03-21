import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../services/tracking_service.dart';

/// Bottom panel with Start/Stop tracking and status readout.
class TrackingControls extends StatelessWidget {
  final int taskId;
  const TrackingControls({super.key, required this.taskId});

  @override
  Widget build(BuildContext context) {
    final tracking = context.watch<TrackingService>();
    final isActive =
        tracking.isTracking && tracking.activeTaskId == taskId;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        border: Border(
          top: BorderSide(color: Theme.of(context).dividerColor),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Status row
            if (isActive && tracking.lastPosition != null) ...[
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _StatusChip(
                    icon: Icons.height,
                    label:
                        '${tracking.lastPosition!.alt?.toStringAsFixed(0) ?? "-"} m',
                  ),
                  _StatusChip(
                    icon: Icons.speed,
                    label:
                        '${tracking.lastPosition!.speed?.toStringAsFixed(1) ?? "-"} m/s',
                  ),
                  _StatusChip(
                    icon: Icons.gps_fixed,
                    label: '${tracking.positionCount} pts',
                  ),
                ],
              ),
              const SizedBox(height: 8),
            ],

            if (tracking.error != null) ...[
              Text(tracking.error!,
                  style: const TextStyle(color: Colors.red, fontSize: 12)),
              const SizedBox(height: 8),
            ],

            // Start / Stop button
            SizedBox(
              width: double.infinity,
              child: isActive
                  ? FilledButton.icon(
                      onPressed: () => tracking.stopTracking(),
                      icon: const Icon(Icons.stop),
                      label: const Text('Stop Tracking'),
                      style: FilledButton.styleFrom(
                        backgroundColor: Colors.red,
                      ),
                    )
                  : FilledButton.icon(
                      onPressed: tracking.isTracking
                          ? null // already tracking a different task
                          : () => tracking.startTracking(taskId),
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('Start Tracking'),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  final IconData icon;
  final String label;
  const _StatusChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: Colors.grey),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 13)),
      ],
    );
  }
}
