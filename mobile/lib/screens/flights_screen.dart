import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../services/igc_service.dart';
import '../services/auth_service.dart';
import '../utils/unit_converter.dart';
import 'flight_detail_screen.dart';

class FlightsScreen extends StatefulWidget {
  const FlightsScreen({super.key});

  @override
  State<FlightsScreen> createState() => _FlightsScreenState();
}

class _FlightsScreenState extends State<FlightsScreen> {
  final Set<String> _selected = {}; // filePaths of selected flights
  bool _selectionMode = false;

  void _toggleFlight(SavedFlight flight) {
    setState(() {
      if (_selected.contains(flight.filePath)) {
        _selected.remove(flight.filePath);
      } else {
        _selected.add(flight.filePath);
      }
      if (_selected.isEmpty) _selectionMode = false;
    });
  }

  void _toggleYear(List<SavedFlight> yearFlights) {
    setState(() {
      final allSelected =
          yearFlights.every((f) => _selected.contains(f.filePath));
      if (allSelected) {
        for (final f in yearFlights) {
          _selected.remove(f.filePath);
        }
      } else {
        for (final f in yearFlights) {
          _selected.add(f.filePath);
        }
      }
      if (_selected.isEmpty) _selectionMode = false;
    });
  }

  void _enterSelectionMode() {
    setState(() => _selectionMode = true);
  }

  void _cancelSelection() {
    setState(() {
      _selected.clear();
      _selectionMode = false;
    });
  }

  Future<void> _deleteSelected(IgcService igc) async {
    final count = _selected.length;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Flights?'),
        content: Text(
            'This will permanently delete $count flight${count == 1 ? '' : 's'}.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      final toDelete = igc.savedFlights
          .where((f) => _selected.contains(f.filePath))
          .toList();
      for (final flight in toDelete) {
        await igc.deleteFlight(flight);
      }
      setState(() {
        _selected.clear();
        _selectionMode = false;
      });
    }
  }

  /// Group flights by year, sorted newest first.
  Map<int, List<SavedFlight>> _groupByYear(List<SavedFlight> flights) {
    final map = <int, List<SavedFlight>>{};
    for (final f in flights) {
      final year = f.date.year;
      map.putIfAbsent(year, () => []).add(f);
    }
    // Sort years descending
    final sorted = Map.fromEntries(
      map.entries.toList()..sort((a, b) => b.key.compareTo(a.key)),
    );
    return sorted;
  }

  @override
  Widget build(BuildContext context) {
    final igc = context.watch<IgcService>();
    final user = context.watch<AuthService>().user;
    final theme = Theme.of(context);
    final flights = igc.savedFlights;
    final grouped = _groupByYear(flights);

    return Scaffold(
      appBar: AppBar(
        title:
            Text(_selectionMode ? '${_selected.length} selected' : 'Flights'),
        leading: _selectionMode
            ? IconButton(
                icon: const Icon(Icons.close),
                onPressed: _cancelSelection,
              )
            : null,
        actions: [
          if (_selectionMode) ...[
            IconButton(
              icon: const Icon(Icons.share),
              tooltip: 'Share selected',
              onPressed: _selected.isNotEmpty
                  ? () {
                      final toShare = igc.savedFlights
                          .where((f) => _selected.contains(f.filePath))
                          .toList();
                      for (final f in toShare) {
                        igc.shareFlight(f);
                      }
                    }
                  : null,
            ),
            IconButton(
              icon: const Icon(Icons.delete, color: Colors.red),
              tooltip: 'Delete selected',
              onPressed:
                  _selected.isNotEmpty ? () => _deleteSelected(igc) : null,
            ),
          ] else ...[
            IconButton(
              icon: const Icon(Icons.checklist),
              tooltip: 'Select flights',
              onPressed: flights.isNotEmpty ? _enterSelectionMode : null,
            ),
            IconButton(
              icon: const Icon(Icons.refresh),
              tooltip: 'Refresh',
              onPressed: () => igc.refresh(),
            ),
          ],
        ],
      ),
      body: flights.isEmpty
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.flight,
                      size: 64,
                      color: theme.colorScheme.onSurfaceVariant.withAlpha(80)),
                  const SizedBox(height: 16),
                  Text(
                    'No flights recorded yet',
                    style: theme.textTheme.titleMedium?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Flights are saved automatically\nwhen you stop tracking.',
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            )
          : ListView(
              padding: EdgeInsets.fromLTRB(
                  16, 16, 16, 16 + MediaQuery.of(context).padding.bottom),
              children: [
                for (final entry in grouped.entries) ...[
                  _YearHeader(
                    year: entry.key,
                    flights: entry.value,
                    selected: _selected,
                    selectionMode: _selectionMode,
                    onToggleYear: () => _toggleYear(entry.value),
                    onEnterSelection: _enterSelectionMode,
                  ),
                  for (final flight in entry.value)
                    _FlightCard(
                      flight: flight,
                      igc: igc,
                      altitudeUnit: user?.altitudeUnit ?? 'ft',
                      speedUnit: user?.speedUnit ?? 'kph',
                      varioUnit: user?.varioUnit ?? 'fpm',
                      selectionMode: _selectionMode,
                      isSelected: _selected.contains(flight.filePath),
                      onToggle: () => _toggleFlight(flight),
                      onLongPress: () {
                        if (!_selectionMode) {
                          _enterSelectionMode();
                          _toggleFlight(flight);
                        }
                      },
                    ),
                  const SizedBox(height: 8),
                ],
              ],
            ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Year header with checkbox
// ═══════════════════════════════════════════════════════════════════════════════

class _YearHeader extends StatelessWidget {
  final int year;
  final List<SavedFlight> flights;
  final Set<String> selected;
  final bool selectionMode;
  final VoidCallback onToggleYear;
  final VoidCallback onEnterSelection;

  const _YearHeader({
    required this.year,
    required this.flights,
    required this.selected,
    required this.selectionMode,
    required this.onToggleYear,
    required this.onEnterSelection,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allSelected = flights.every((f) => selected.contains(f.filePath));
    final someSelected = flights.any((f) => selected.contains(f.filePath));

    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 4),
      child: Row(
        children: [
          if (selectionMode)
            Checkbox(
              value: allSelected
                  ? true
                  : someSelected
                      ? null
                      : false,
              tristate: true,
              onChanged: (_) => onToggleYear(),
            ),
          Text(
            '$year',
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.bold,
              color: theme.colorScheme.primary,
            ),
          ),
          const SizedBox(width: 8),
          Text(
            '${flights.length} flight${flights.length == 1 ? '' : 's'}',
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Flight card with optional checkbox
// ═══════════════════════════════════════════════════════════════════════════════

class _FlightCard extends StatelessWidget {
  final SavedFlight flight;
  final IgcService igc;
  final String altitudeUnit;
  final String speedUnit;
  final String varioUnit;
  final bool selectionMode;
  final bool isSelected;
  final VoidCallback onToggle;
  final VoidCallback onLongPress;

  const _FlightCard({
    required this.flight,
    required this.igc,
    required this.altitudeUnit,
    required this.speedUnit,
    required this.varioUnit,
    required this.selectionMode,
    required this.isSelected,
    required this.onToggle,
    required this.onLongPress,
  });

  String _formatDuration(Duration d) {
    final h = d.inHours;
    final m = d.inMinutes % 60;
    if (h > 0) return '${h}h ${m}m';
    return '${m}m';
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final dateFmt = DateFormat('MMM d');
    final timeFmt = DateFormat('HH:mm');

    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      color:
          isSelected ? theme.colorScheme.primaryContainer.withAlpha(120) : null,
      child: InkWell(
        borderRadius: BorderRadius.circular(12),
        onTap: selectionMode ? onToggle : () => _showFlightDetails(context),
        onLongPress: onLongPress,
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              // Checkbox in selection mode
              if (selectionMode)
                Checkbox(
                  value: isSelected,
                  onChanged: (_) => onToggle(),
                  visualDensity: VisualDensity.compact,
                ),

              // Flight info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Date and time
                    Row(
                      children: [
                        Icon(Icons.calendar_today,
                            size: 14, color: theme.colorScheme.primary),
                        const SizedBox(width: 6),
                        Text(
                          dateFmt.format(flight.date),
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          timeFmt.format(flight.date),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                        if (!selectionMode) ...[
                          const Spacer(),
                          IconButton(
                            icon: const Icon(Icons.share, size: 18),
                            tooltip: 'Share IGC file',
                            onPressed: () => igc.shareFlight(flight),
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            constraints: const BoxConstraints(),
                          ),
                        ],
                      ],
                    ),
                    const SizedBox(height: 8),
                    // Stats row
                    Row(
                      children: [
                        _FlightStat(
                          icon: Icons.timer,
                          label: 'Duration',
                          value: _formatDuration(flight.duration),
                        ),
                        const SizedBox(width: 20),
                        _FlightStat(
                          icon: Icons.height,
                          label: 'Max Alt',
                          value: UnitConverter.formatAltitude(
                            flight.maxAltitude,
                            altitudeUnit,
                          ),
                        ),
                        const SizedBox(width: 20),
                        _FlightStat(
                          icon: Icons.speed,
                          label: 'Max Speed',
                          value: UnitConverter.formatSpeed(
                            flight.maxSpeed,
                            speedUnit,
                          ),
                        ),
                        const SizedBox(width: 20),
                        _FlightStat(
                          icon: Icons.trending_up,
                          label: 'Max Climb',
                          value: UnitConverter.formatVario(
                            flight.maxClimbRate,
                            varioUnit,
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showFlightDetails(BuildContext context) {
    // Navigate to the flight detail map screen
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => FlightDetailScreen(flight: flight),
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Flight stat chip
// ═══════════════════════════════════════════════════════════════════════════════

class _FlightStat extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;

  const _FlightStat({
    required this.icon,
    required this.label,
    required this.value,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: theme.colorScheme.primary),
            const SizedBox(width: 4),
            Text(
              value,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
          ],
        ),
        Text(
          label,
          style: theme.textTheme.labelSmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    );
  }
}
