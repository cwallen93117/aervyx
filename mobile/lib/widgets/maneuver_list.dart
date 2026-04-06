import 'package:flutter/material.dart';

import '../models/driver_route.dart';

/// Scrollable list of turn-by-turn maneuver instructions.
class ManeuverList extends StatelessWidget {
  final List<RouteManeuver> maneuvers;
  final int currentIndex;

  const ManeuverList({
    super.key,
    required this.maneuvers,
    this.currentIndex = 0,
  });

  String _formatDistance(double km) {
    if (km < 1) return '${(km * 1000).toInt()} m';
    return '${km.toStringAsFixed(1)} km';
  }

  IconData _maneuverIcon(int type) {
    switch (type) {
      case 1:
        return Icons.arrow_upward;
      case 2:
        return Icons.turn_slight_right;
      case 3:
        return Icons.turn_right;
      case 4:
        return Icons.turn_sharp_right_outlined;
      case 5:
        return Icons.u_turn_right;
      case 6:
        return Icons.turn_sharp_left_outlined;
      case 7:
        return Icons.turn_left;
      case 8:
        return Icons.turn_slight_left;
      case 9:
        return Icons.u_turn_left;
      case 10:
        return Icons.roundabout_right;
      case 24:
        return Icons.flag;
      default:
        return Icons.arrow_forward;
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return ListView.separated(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: maneuvers.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (context, index) {
        final m = maneuvers[index];
        final isCurrent = index == currentIndex;

        return Container(
          color: isCurrent
              ? theme.colorScheme.primaryContainer.withAlpha(60)
              : null,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Icon(
                _maneuverIcon(m.type),
                size: 20,
                color: isCurrent
                    ? theme.colorScheme.primary
                    : theme.colorScheme.onSurfaceVariant,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      m.instruction,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: isCurrent ? FontWeight.w600 : null,
                      ),
                    ),
                    if (m.streetName != null)
                      Text(
                        m.streetName!,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                  ],
                ),
              ),
              Text(
                _formatDistance(m.distanceKm),
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
