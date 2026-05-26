import 'package:flutter/material.dart';

enum LiveMapStyle {
  map(
    label: 'Map',
    icon: Icons.map_outlined,
    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    maxZoom: 19,
  ),
  satellite(
    label: 'Satellite',
    icon: Icons.satellite_alt,
    urlTemplate:
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    maxZoom: 18,
  );

  const LiveMapStyle({
    required this.label,
    required this.icon,
    required this.urlTemplate,
    required this.maxZoom,
  });

  final String label;
  final IconData icon;
  final String urlTemplate;
  final double maxZoom;
}

class LiveMapStyleDropdown extends StatelessWidget {
  final LiveMapStyle value;
  final ValueChanged<LiveMapStyle> onChanged;

  const LiveMapStyleDropdown({
    super.key,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      color: theme.colorScheme.surface.withAlpha(235),
      borderRadius: BorderRadius.circular(8),
      elevation: 3,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8),
        child: DropdownButtonHideUnderline(
          child: DropdownButton<LiveMapStyle>(
            value: value,
            borderRadius: BorderRadius.circular(8),
            icon: const Icon(Icons.expand_more),
            onChanged: (style) {
              if (style != null) onChanged(style);
            },
            items: LiveMapStyle.values
                .map(
                  (style) => DropdownMenuItem(
                    value: style,
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(style.icon, size: 18),
                        const SizedBox(width: 8),
                        Text(style.label),
                      ],
                    ),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }
}
