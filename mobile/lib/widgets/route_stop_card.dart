import 'package:flutter/material.dart';

import '../models/driver_route.dart';

/// Card showing a single stop on the driver pickup route.
class RouteStopCard extends StatelessWidget {
  final RouteStop stop;
  final int index;
  final bool isCurrent;
  final VoidCallback? onPickUp;
  final VoidCallback? onSkip;

  const RouteStopCard({
    super.key,
    required this.stop,
    required this.index,
    required this.isCurrent,
    this.onPickUp,
    this.onSkip,
  });

  Color _statusColor() {
    switch (stop.status) {
      case 'picked_up':
        return Colors.blue;
      case 'ready':
        return Colors.green;
      case 'landed':
      default:
        return Colors.grey;
    }
  }

  String _statusLabel() {
    switch (stop.status) {
      case 'picked_up':
        return 'PICKED UP';
      case 'ready':
        return 'READY';
      case 'landed':
        final mins = stop.minutesUntilReady;
        if (mins <= 0) return 'READY';
        return '${mins}m wait';
      default:
        return stop.status.toUpperCase();
    }
  }

  String _formatEta() {
    final local = stop.eta.toLocal();
    return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
      color: isCurrent
          ? theme.colorScheme.primaryContainer.withAlpha(100)
          : stop.status == 'picked_up'
              ? theme.colorScheme.surfaceContainerHighest.withAlpha(80)
              : null,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        child: Row(
          children: [
            // Stop number
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: _statusColor(),
                shape: BoxShape.circle,
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
            const SizedBox(width: 12),

            // Pilot info
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    stop.pilotName,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                      decoration: stop.status == 'picked_up'
                          ? TextDecoration.lineThrough
                          : null,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Row(
                    children: [
                      Text(
                        'ETA ${_formatEta()}',
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(width: 10),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 6, vertical: 1),
                        decoration: BoxDecoration(
                          color: _statusColor().withAlpha(30),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          _statusLabel(),
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.w600,
                            color: _statusColor(),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Action buttons for current stop
            if (isCurrent && stop.status != 'picked_up') ...[
              if (onSkip != null)
                TextButton(
                  onPressed: onSkip,
                  child: const Text('Skip'),
                ),
              if (onPickUp != null)
                FilledButton.icon(
                  icon: const Icon(Icons.check, size: 16),
                  label: const Text('Pick Up'),
                  onPressed: onPickUp,
                  style: FilledButton.styleFrom(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                    textStyle: const TextStyle(fontSize: 12),
                  ),
                ),
            ],
          ],
        ),
      ),
    );
  }
}
