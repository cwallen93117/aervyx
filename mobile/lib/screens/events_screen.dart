import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:intl/intl.dart';
import 'package:latlong2/latlong.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';
import '../widgets/live_map_style.dart';
import '../widgets/map_scale_bar.dart';

String _dateValue(DateTime date) => DateFormat('yyyy-MM-dd').format(date);

Map<String, dynamic> defaultEventSettings([DateTime? today]) {
  final start = DateUtils.dateOnly(today ?? DateTime.now());
  return {
    'name': '',
    'location': '',
    'starts_on': _dateValue(start),
    'ends_on': _dateValue(start.add(const Duration(days: 6))),
    'timezone': 'UTC',
    'scoring_formula': 'GAP2021',
    'nominal_distance_km': 60.0,
    'nominal_time_hours': 1.5,
    'nominal_launch': 0.95,
    'minimum_distance_km': 5.0,
    'nominal_goal_percent': 0.3,
    'score_back_time_minutes': 15,
    'goal_ss_penalty': 0.0,
    'day_quality_override': 0.0,
    'time_points_if_not_in_goal': 1.0,
    'jump_the_gun_factor': 0.0,
    'jump_the_gun_max_seconds': 0,
    'default_start_gate_count': 5,
    'default_start_gate_interval_seconds': 900,
    'stopped_glide_bonus': 0.0,
    'use_1000_points_for_max_day_quality': false,
    'normalize_1000_before_day_quality': false,
    'use_distance_points': true,
    'use_time_points': true,
    'use_leading_points': true,
    'use_arrival_position_points': false,
    'use_arrival_time_points': false,
    'use_departure_points': false,
    'use_difficulty_for_distance_points': true,
    'use_distance_squared_for_lc': false,
    'use_semi_circle_control_zone_for_goal_line': true,
    'use_proportional_leading_weight_if_nobody_in_goal': true,
    'redistribute_removed_time_points_as_distance_points': false,
    'use_best_score_for_ftv_validity': true,
    'use_constant_leading_weight': false,
    'use_pwca2019_for_lc': false,
    'use_flat_decline_of_timepoints': false,
    'scoring_altitude': 'GPS',
    'final_glide_decelerator': 'none',
    'no_final_glide_decelerator_reason': '',
    'min_time_span_for_valid_task_minutes': 60,
    'leading_weight_factor': 1.0,
    'turnpoint_radius_tolerance': 0.0005,
    'turnpoint_radius_minimum_absolute_tolerance_m': 5.0,
    'number_of_decimals_task_results': 2,
    'number_of_decimals_competition_results': 1,
    'visible_airspace_classes_json': <String>[
      'B',
      'C',
      'D',
      'P',
      'Q',
      'R',
      'TFR',
      'OTHER'
    ],
    'show_restricted_fields': true,
    'penalties_json': <String, dynamic>{},
    'is_public_tracking': false,
    'visibility': 'private',
  };
}

Map<String, dynamic> _formulaPreset(String formula) {
  final preset = <String, dynamic>{
    'nominal_goal_percent': 0.2,
    'nominal_distance_km': 60.0,
    'nominal_time_hours': 1.5,
    'nominal_launch': 0.95,
    'minimum_distance_km': 5.0,
    'score_back_time_minutes': 15,
    'goal_ss_penalty': 1.0,
    'stopped_glide_bonus': 0.0,
    'jump_the_gun_factor': 0.0,
    'jump_the_gun_max_seconds': 0,
    'time_points_if_not_in_goal': 0.0,
    'leading_weight_factor': 1.0,
    'turnpoint_radius_tolerance': 0.005,
    'turnpoint_radius_minimum_absolute_tolerance_m': 5.0,
    'number_of_decimals_task_results': 1,
    'number_of_decimals_competition_results': 0,
    'scoring_altitude': 'GPS',
    'final_glide_decelerator': 'none',
    'use_distance_points': true,
    'use_time_points': true,
    'use_leading_points': false,
    'use_arrival_position_points': false,
    'use_arrival_time_points': false,
    'use_departure_points': false,
    'use_1000_points_for_max_day_quality': false,
    'normalize_1000_before_day_quality': false,
    'use_difficulty_for_distance_points': true,
    'use_distance_squared_for_lc': false,
    'use_semi_circle_control_zone_for_goal_line': false,
    'use_proportional_leading_weight_if_nobody_in_goal': false,
    'redistribute_removed_time_points_as_distance_points': false,
    'use_best_score_for_ftv_validity': false,
    'use_constant_leading_weight': false,
    'use_pwca2019_for_lc': false,
    'use_flat_decline_of_timepoints': false,
    'day_quality_override': 0.0,
    'min_time_span_for_valid_task_minutes': 0,
  };
  switch (formula) {
    case 'GAP2025':
      preset.addAll({
        'nominal_goal_percent': 0.3,
        'nominal_distance_km': 50.0,
        'nominal_launch': 0.96,
        'goal_ss_penalty': 0.0,
        'time_points_if_not_in_goal': 0.8,
        'use_leading_points': true,
        'use_arrival_position_points': true,
        'use_flat_decline_of_timepoints': true,
        'redistribute_removed_time_points_as_distance_points': true,
        'use_distance_squared_for_lc': true,
        'use_semi_circle_control_zone_for_goal_line': true,
        'use_best_score_for_ftv_validity': true,
        'stopped_glide_bonus': 5.0,
        'jump_the_gun_factor': 2.0,
        'jump_the_gun_max_seconds': 300,
        'min_time_span_for_valid_task_minutes': 45,
        'number_of_decimals_competition_results': 1,
      });
    case 'GAP2021':
    case 'GAP2020':
      preset.addAll({
        'use_flat_decline_of_timepoints': true,
        'redistribute_removed_time_points_as_distance_points': true,
        'use_distance_squared_for_lc': true,
        'use_semi_circle_control_zone_for_goal_line': true,
        'time_points_if_not_in_goal': 0.8,
        'stopped_glide_bonus': 5.0,
        'jump_the_gun_factor': 2.0,
        'jump_the_gun_max_seconds': 300,
        'min_time_span_for_valid_task_minutes': 45,
      });
    case 'GAP2018':
      preset.addAll({
        'use_distance_squared_for_lc': true,
        'use_semi_circle_control_zone_for_goal_line': true,
        'stopped_glide_bonus': 4.0,
        'jump_the_gun_factor': 2.0,
        'jump_the_gun_max_seconds': 300,
        'min_time_span_for_valid_task_minutes': 45,
      });
    case 'GAP2016':
      preset.addAll({
        'use_arrival_position_points': true,
        'stopped_glide_bonus': 4.0,
        'jump_the_gun_factor': 2.0,
        'jump_the_gun_max_seconds': 300,
        'min_time_span_for_valid_task_minutes': 45,
      });
    case 'GAP2008':
      preset.addAll({
        'use_arrival_position_points': true,
        'use_departure_points': true,
      });
    case 'OzGAP2005':
      preset.addAll({
        'use_arrival_time_points': true,
        'use_departure_points': true,
      });
    case 'PWC2016':
      preset.addAll({
        'use_leading_points': true,
        'use_distance_squared_for_lc': true,
        'score_back_time_minutes': 5,
      });
  }
  return preset;
}

class EventSummary {
  final int id;
  final Map<String, dynamic> settings;

  EventSummary({
    required this.id,
    required String name,
    required String startsOn,
    required String endsOn,
    String location = '',
    Map<String, dynamic> settings = const {},
  }) : settings = Map.unmodifiable({
          ...defaultEventSettings(),
          ...settings,
          'name': name,
          'location': location,
          'starts_on': startsOn,
          'ends_on': endsOn,
        });

  EventSummary._(this.id, Map<String, dynamic> settings)
      : settings = Map.unmodifiable(settings);

  String get name => settings['name'] as String? ?? 'Event';
  String get location => settings['location'] as String? ?? '';
  String get startsOn => settings['starts_on'] as String? ?? '';
  String get endsOn => settings['ends_on'] as String? ?? '';

  factory EventSummary.draft([DateTime? today]) =>
      EventSummary._(0, defaultEventSettings(today));

  factory EventSummary.fromJson(Map<String, dynamic> json) {
    return EventSummary._(
      json['id'] as int,
      {...defaultEventSettings(), ...json}..remove('id'),
    );
  }

  Map<String, dynamic> toPayload() {
    final defaults = defaultEventSettings();
    return {
      for (final key in defaults.keys) key: settings[key] ?? defaults[key]
    };
  }
}

class TurnpointSourceSummary {
  final int id;
  final String filename;
  final int turnpointCount;

  const TurnpointSourceSummary({
    required this.id,
    required this.filename,
    required this.turnpointCount,
  });

  factory TurnpointSourceSummary.fromJson(Map<String, dynamic> json) {
    return TurnpointSourceSummary(
      id: json['id'] as int,
      filename: json['filename'] as String? ?? 'Waypoints',
      turnpointCount: json['turnpoint_count'] as int? ?? 0,
    );
  }
}

class EventWaypoint {
  final int id;
  final String name;
  final double latitude;
  final double longitude;

  const EventWaypoint({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  factory EventWaypoint.fromJson(Map<String, dynamic> json) {
    return EventWaypoint(
      id: json['id'] as int,
      name: json['name'] as String? ?? 'Waypoint',
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
    );
  }
}

class EventTask {
  final int? id;
  final String name;
  final String taskDate;
  final String taskType;
  final String status;
  final int startGateCount;
  final int? startGateIntervalSeconds;
  final List<EventTaskPoint> points;

  const EventTask({
    this.id,
    required this.name,
    required this.taskDate,
    required this.taskType,
    this.status = 'draft',
    this.startGateCount = 1,
    this.startGateIntervalSeconds,
    this.points = const [],
  });

  factory EventTask.fromJson(Map<String, dynamic> json) {
    return EventTask(
      id: json['id'] as int?,
      name: json['name'] as String? ?? 'Task',
      taskDate: json['task_date'] as String? ?? '',
      taskType: json['task_type'] as String? ?? 'race_to_goal_with_gates',
      status: json['status'] as String? ?? 'draft',
      startGateCount: json['start_gate_count'] as int? ?? 1,
      startGateIntervalSeconds: json['start_gate_interval_seconds'] as int?,
      points: (json['points'] as List<dynamic>? ?? const [])
          .map((item) => EventTaskPoint.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  EventTask copyWith({
    String? name,
    String? taskDate,
    String? taskType,
    int? startGateCount,
    int? startGateIntervalSeconds,
    List<EventTaskPoint>? points,
  }) {
    return EventTask(
      id: id,
      name: name ?? this.name,
      taskDate: taskDate ?? this.taskDate,
      taskType: taskType ?? this.taskType,
      status: status,
      startGateCount: startGateCount ?? this.startGateCount,
      startGateIntervalSeconds:
          startGateIntervalSeconds ?? this.startGateIntervalSeconds,
      points: points ?? this.points,
    );
  }

  Map<String, dynamic> toPayload() => {
        'name': name,
        'task_date': taskDate.isEmpty ? null : taskDate,
        'is_practice': false,
        'status': status,
        'task_type': taskType,
        'task_start_time': null,
        'task_finish_time': null,
        'start_open_time': null,
        'start_close_time': null,
        'start_gate_count': startGateCount,
        'start_gate_interval_seconds': startGateIntervalSeconds,
        'points': points
            .asMap()
            .entries
            .map((entry) => entry.value.toPayload(entry.key + 1))
            .toList(),
      };
}

class EventTaskPoint {
  final int turnpointId;
  final String name;
  final double latitude;
  final double longitude;
  final String pointType;
  final String direction;
  final double radiusMeters;

  const EventTaskPoint({
    required this.turnpointId,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.pointType,
    required this.direction,
    required this.radiusMeters,
  });

  factory EventTaskPoint.fromWaypoint(
    EventWaypoint waypoint,
    int index,
  ) {
    final type = index == 0 ? 'start' : 'turnpoint';
    return EventTaskPoint(
      turnpointId: waypoint.id,
      name: waypoint.name,
      latitude: waypoint.latitude,
      longitude: waypoint.longitude,
      pointType: type,
      direction: type == 'start' ? 'exit' : 'enter',
      radiusMeters: defaultRadiusForPointType(type),
    );
  }

  factory EventTaskPoint.fromJson(Map<String, dynamic> json) {
    final type = json['point_type'] as String? ?? 'turnpoint';
    return EventTaskPoint(
      turnpointId: json['turnpoint_id'] as int? ?? 0,
      name: json['name'] as String? ?? 'Waypoint',
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
      pointType: type,
      direction:
          json['direction'] as String? ?? defaultDirectionForPointType(type),
      radiusMeters: (json['radius_m'] as num?)?.toDouble() ??
          defaultRadiusForPointType(type),
    );
  }

  EventTaskPoint copyWith({
    String? pointType,
    String? direction,
    double? radiusMeters,
  }) {
    final nextType = pointType ?? this.pointType;
    return EventTaskPoint(
      turnpointId: turnpointId,
      name: name,
      latitude: latitude,
      longitude: longitude,
      pointType: nextType,
      direction: direction ??
          (pointType == null
              ? this.direction
              : defaultDirectionForPointType(nextType)),
      radiusMeters: radiusMeters ??
          (pointType == null
              ? this.radiusMeters
              : defaultRadiusForPointType(nextType)),
    );
  }

  Map<String, dynamic> toPayload(int position) => {
        'position': position,
        'point_type': pointType,
        'direction': direction,
        'radius_m': radiusMeters,
        'turnpoint_id': turnpointId,
        'name': name,
        'latitude': latitude,
        'longitude': longitude,
      };
}

String defaultDirectionForPointType(String type) =>
    type == 'start' ? 'exit' : 'enter';

double defaultRadiusForPointType(String type) {
  switch (type) {
    case 'start':
      return 5000;
    case 'turnpoint':
      return 1000;
    case 'goal':
    case 'ess':
    default:
      return 400;
  }
}

class EventsScreen extends StatefulWidget {
  final ApiService api;
  final bool canManageEvents;

  const EventsScreen({
    super.key,
    required this.api,
    this.canManageEvents = false,
  });

  @override
  State<EventsScreen> createState() => _EventsScreenState();
}

class _EventsScreenState extends State<EventsScreen> {
  bool _loading = true;
  String? _error;
  List<EventSummary> _events = [];

  @override
  void initState() {
    super.initState();
    _loadEvents();
  }

  Future<void> _loadEvents() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.api.getList(ApiConfig.eventsPath);
      if (!mounted) return;
      setState(() {
        _events = rows
            .whereType<Map<String, dynamic>>()
            .map(EventSummary.fromJson)
            .toList();
      });
    } catch (error) {
      if (mounted) setState(() => _error = 'Could not load events.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _editEvent(EventSummary event) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => EventEditorScreen(api: widget.api, event: event),
      ),
    );
    await _loadEvents();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Events')),
      floatingActionButton: widget.canManageEvents
          ? FloatingActionButton.extended(
              key: const Key('new-event-button'),
              onPressed: () => _editEvent(EventSummary.draft()),
              icon: const Icon(Icons.add),
              label: const Text('New event'),
            )
          : null,
      body: RefreshIndicator(
        onRefresh: _loadEvents,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('Events', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loading)
              const Center(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: CircularProgressIndicator(),
                ),
              )
            else if (_error != null)
              Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  _error!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              )
            else if (_events.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('No events are available.'),
              )
            else
              ..._events.map(
                (event) => Card(
                  child: ListTile(
                    leading: const Icon(Icons.event_outlined),
                    title: Text(event.name),
                    subtitle: Text([
                      if (event.location.isNotEmpty) event.location,
                      '${event.startsOn} - ${event.endsOn}',
                    ].join('\n')),
                    trailing: widget.canManageEvents
                        ? IconButton(
                            key: Key('edit-event-${event.id}'),
                            onPressed: () => _editEvent(event),
                            icon: const Icon(Icons.edit_outlined),
                            tooltip: 'Edit event settings',
                          )
                        : null,
                    onTap: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => EventTaskBuilderScreen(
                            api: widget.api,
                            event: event,
                            canEdit: widget.canManageEvents,
                          ),
                        ),
                      );
                      await _loadEvents();
                    },
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class EventEditorScreen extends StatefulWidget {
  final ApiService api;
  final EventSummary event;

  const EventEditorScreen({
    super.key,
    required this.api,
    required this.event,
  });

  @override
  State<EventEditorScreen> createState() => _EventEditorScreenState();
}

class _EventEditorScreenState extends State<EventEditorScreen> {
  static const _formulaOptions = <String>[
    'GAP2025',
    'GAP2021',
    'GAP2020',
    'GAP2018',
    'GAP2016',
    'GAP2008',
    'OzGAP2005',
    'PWC2016',
  ];
  static const _airspaceClasses = <String>[
    'B',
    'C',
    'D',
    'P',
    'Q',
    'R',
    'TFR',
    'OTHER',
  ];

  final _formKey = GlobalKey<FormState>();
  late final Map<String, dynamic> _settings;
  final List<Map<String, dynamic>> _presets = [];
  int? _savedEventId;
  int _formRevision = 0;
  bool _saving = false;

  bool get _isNew => (_savedEventId ?? widget.event.id) == 0;

  @override
  void initState() {
    super.initState();
    _settings = Map<String, dynamic>.from(widget.event.toPayload());
    if (!_isNew) _loadPresets();
  }

  String _text(String key) => _settings[key]?.toString() ?? '';
  bool _bool(String key) => _settings[key] as bool? ?? false;

  Future<void> _loadPresets() async {
    try {
      final rows = await widget.api.getList(
        ApiConfig.eventScoringPresetsPath(widget.event.id),
      );
      if (!mounted) return;
      setState(() {
        _presets
          ..clear()
          ..addAll(rows
              .whereType<Map<String, dynamic>>()
              .map((row) => Map<String, dynamic>.from(row)));
      });
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not load penalty presets.')),
      );
    }
  }

  void _addPreset() {
    setState(() {
      _presets.add({
        'id': 'preset-${DateTime.now().microsecondsSinceEpoch}',
        'label': '',
        'penalty_type': 'percentage',
        'value': 0.0,
        'reason': '',
      });
    });
  }

  Future<void> _pickDate(String key) async {
    final initial = DateTime.tryParse(_text(key)) ?? DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime(2000),
      lastDate: DateTime(2100),
      helpText: key == 'starts_on' ? 'SELECT START DATE' : 'SELECT END DATE',
    );
    if (picked != null) setState(() => _settings[key] = _dateValue(picked));
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    final startsOn = DateTime.parse(_text('starts_on'));
    final endsOn = DateTime.parse(_text('ends_on'));
    if (endsOn.isBefore(startsOn)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('End date must be on or after start date.')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      final eventId = _savedEventId ?? widget.event.id;
      final saved = eventId == 0
          ? await widget.api.post(ApiConfig.eventsPath, body: _settings)
          : await widget.api.put(
              ApiConfig.eventPath(eventId),
              body: _settings,
            );
      final savedEventId = saved['id'] as int;
      _savedEventId = savedEventId;
      await widget.api.patch(
        ApiConfig.eventScoringPresetsPath(savedEventId),
        body: {
          'presets': _presets
              .where((preset) =>
                  (preset['label'] as String? ?? '').trim().isNotEmpty)
              .map((preset) {
            final label = (preset['label'] as String).trim();
            return {...preset, 'label': label, 'reason': label};
          }).toList(),
        },
      );
      if (!mounted) return;
      Navigator.of(context).pop(EventSummary.fromJson(saved));
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text('Could not ${_isNew ? 'create' : 'save'} event.')),
      );
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _textField(
    String key,
    String label, {
    String? hint,
    bool required = false,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: Key('event-$key'),
        initialValue: _text(key),
        decoration: InputDecoration(labelText: label, hintText: hint),
        textCapitalization: TextCapitalization.sentences,
        onChanged: (value) => _settings[key] = value,
        validator: required
            ? (value) =>
                value == null || value.trim().isEmpty ? 'Enter $label.' : null
            : null,
      ),
    );
  }

  Widget _numberField(
    String key,
    String label, {
    bool integer = false,
    double? minimum,
    double? maximum,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextFormField(
        key: Key('event-$key-$_formRevision'),
        initialValue: _text(key),
        decoration: InputDecoration(labelText: label),
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        onChanged: (value) {
          final parsed = num.tryParse(value);
          if (parsed != null) {
            _settings[key] = integer ? parsed.toInt() : parsed;
          }
        },
        validator: (value) {
          final parsed = num.tryParse(value ?? '');
          if (parsed == null) return 'Enter a number.';
          if (minimum != null && parsed < minimum) {
            return 'Minimum is $minimum.';
          }
          if (maximum != null && parsed > maximum) {
            return 'Maximum is $maximum.';
          }
          return null;
        },
      ),
    );
  }

  Widget _switch(String key, String label) => SwitchListTile.adaptive(
        contentPadding: EdgeInsets.zero,
        title: Text(label),
        value: _bool(key),
        onChanged: (value) => setState(() => _settings[key] = value),
      );

  Widget _dropdown(
    String key,
    String label,
    List<DropdownMenuItem<String>> items, {
    void Function(String value)? onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: DropdownButtonFormField<String>(
        key: Key('event-$key-$_formRevision'),
        isExpanded: true,
        initialValue: _text(key),
        decoration: InputDecoration(labelText: label),
        items: items,
        onChanged: (value) {
          if (value != null) {
            setState(() {
              _settings[key] = value;
              onChanged?.call(value);
            });
          }
        },
      ),
    );
  }

  Widget _dateField(String key, String label) {
    final date = DateTime.tryParse(_text(key));
    return ListTile(
      key: Key('event-$key'),
      contentPadding: EdgeInsets.zero,
      leading: const Icon(Icons.calendar_month_outlined),
      title: Text(label),
      subtitle: Text(
          date == null ? 'Choose a date' : DateFormat.yMMMMd().format(date)),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => _pickDate(key),
    );
  }

  Widget _section(
    String title,
    String subtitle,
    List<Widget> children, {
    bool expanded = false,
  }) {
    return Card(
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        initiallyExpanded: expanded,
        maintainState: true,
        title: Text(title),
        subtitle: Text(subtitle),
        childrenPadding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
        children: children,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final currentFormula = _text('scoring_formula');
    final formulaOptions = [
      ..._formulaOptions,
      if (!_formulaOptions.contains(currentFormula)) currentFormula,
    ];
    final selectedAirspaceClasses =
        (_settings['visible_airspace_classes_json'] as List<dynamic>? ??
                const [])
            .map((value) => value.toString())
            .toSet();
    return Scaffold(
      appBar: AppBar(
        title: Text(_isNew ? 'New event' : 'Event settings'),
        actions: [
          IconButton(
            onPressed: _saving ? null : _save,
            icon: const Icon(Icons.save_outlined),
            tooltip: _isNew ? 'Create event' : 'Save event',
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          key: const Key('event-settings-form'),
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 96),
          children: [
            _section(
              'Event details',
              'Name, location, and who can view it',
              [
                _textField('name', 'Event name', required: true),
                _textField('location', 'Location'),
                _dropdown(
                  'visibility',
                  'Publicly viewable',
                  const [
                    DropdownMenuItem(value: 'public', child: Text('Public')),
                    DropdownMenuItem(
                      value: 'users',
                      child: Text('All Aervyx users'),
                    ),
                    DropdownMenuItem(
                      value: 'participants',
                      child: Text('Event participants'),
                    ),
                    DropdownMenuItem(
                        value: 'private', child: Text('Not viewable')),
                  ],
                ),
                _switch('is_public_tracking', 'Public live tracking'),
              ],
              expanded: true,
            ),
            _section(
              'Schedule',
              '${_text('starts_on')} to ${_text('ends_on')}',
              [
                _dateField('starts_on', 'Starts on'),
                _dateField('ends_on', 'Ends on'),
                const SizedBox(height: 8),
                _textField(
                  'timezone',
                  'Timezone',
                  hint: 'America/New_York',
                  required: true,
                ),
                _numberField(
                  'default_start_gate_count',
                  'Default start gates',
                  integer: true,
                  minimum: 1,
                ),
                _numberField(
                  'default_start_gate_interval_seconds',
                  'Default gate interval (seconds)',
                  integer: true,
                  minimum: 0,
                ),
              ],
              expanded: true,
            ),
            _section(
              'Formula and points',
              'Scoring formula, weights, and penalties',
              [
                _dropdown(
                  'scoring_formula',
                  'Scoring formula',
                  formulaOptions
                      .map((value) => DropdownMenuItem(
                            value: value,
                            child: Text(_formulaOptions.contains(value)
                                ? value
                                : 'Custom: $value'),
                          ))
                      .toList(),
                  onChanged: (value) {
                    if (_formulaOptions.contains(value)) {
                      _settings.addAll(_formulaPreset(value));
                      _formRevision++;
                    }
                  },
                ),
                _numberField(
                  'nominal_goal_percent',
                  'Nominal goal fraction',
                  minimum: 0,
                  maximum: 1,
                ),
                _numberField(
                  'score_back_time_minutes',
                  'Score-back time (minutes)',
                  integer: true,
                  minimum: 0,
                ),
                _numberField(
                  'goal_ss_penalty',
                  'Goal SS penalty',
                  minimum: 0,
                ),
                _numberField(
                  'stopped_glide_bonus',
                  'Stopped glide bonus',
                  minimum: 0,
                ),
                _numberField(
                  'jump_the_gun_factor',
                  'Jump-the-gun factor',
                  minimum: 0,
                ),
                _numberField(
                  'jump_the_gun_max_seconds',
                  'Jump-the-gun maximum (seconds)',
                  integer: true,
                  minimum: 0,
                ),
                _switch('use_distance_points', 'Distance points'),
                _switch('use_time_points', 'Time points'),
                _switch('use_leading_points', 'Leading points'),
                _switch(
                    'use_arrival_position_points', 'Arrival position points'),
                _switch('use_arrival_time_points', 'Arrival time points'),
                _switch('use_departure_points', 'Departure points'),
              ],
            ),
            _section(
              'Penalty presets',
              _presets.isEmpty
                  ? 'No presets configured'
                  : '${_presets.length} configured',
              [
                ..._presets.asMap().entries.map((entry) {
                  final index = entry.key;
                  final preset = entry.value;
                  return Card.outlined(
                    key: ValueKey(preset['id']),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(12, 12, 4, 12),
                      child: Column(
                        children: [
                          TextFormField(
                            initialValue: preset['label'] as String? ?? '',
                            decoration:
                                const InputDecoration(labelText: 'Preset name'),
                            onChanged: (value) => preset['label'] = value,
                          ),
                          const SizedBox(height: 12),
                          Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Expanded(
                                child: DropdownButtonFormField<String>(
                                  initialValue:
                                      preset['penalty_type'] as String? ??
                                          'percentage',
                                  decoration:
                                      const InputDecoration(labelText: 'Type'),
                                  items: const [
                                    DropdownMenuItem(
                                      value: 'percentage',
                                      child: Text('% penalty'),
                                    ),
                                    DropdownMenuItem(
                                      value: 'fixed',
                                      child: Text('Fixed points'),
                                    ),
                                  ],
                                  onChanged: (value) {
                                    if (value != null) {
                                      preset['penalty_type'] = value;
                                    }
                                  },
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: TextFormField(
                                  initialValue: preset['value'].toString(),
                                  decoration: const InputDecoration(
                                      labelText: 'Amount'),
                                  keyboardType:
                                      const TextInputType.numberWithOptions(
                                    decimal: true,
                                  ),
                                  onChanged: (value) {
                                    final parsed = double.tryParse(value);
                                    if (parsed != null) {
                                      preset['value'] = parsed;
                                    }
                                  },
                                  validator: (value) {
                                    final parsed = double.tryParse(value ?? '');
                                    return parsed == null || parsed < 0
                                        ? 'Use 0 or more.'
                                        : null;
                                  },
                                ),
                              ),
                              IconButton(
                                onPressed: () => setState(
                                  () => _presets.removeAt(index),
                                ),
                                icon: const Icon(Icons.delete_outline),
                                tooltip: 'Remove preset',
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                }),
                Align(
                  alignment: Alignment.centerLeft,
                  child: OutlinedButton.icon(
                    onPressed: _addPreset,
                    icon: const Icon(Icons.add),
                    label: const Text('Add preset'),
                  ),
                ),
              ],
            ),
            _section(
              'Nominal values',
              'Expected distance, duration, launch, and minimum distance',
              [
                _numberField(
                  'nominal_distance_km',
                  'Nominal distance (km)',
                  minimum: 0,
                ),
                _numberField(
                  'nominal_time_hours',
                  'Nominal time (hours)',
                  minimum: 0,
                ),
                _numberField(
                  'nominal_launch',
                  'Nominal launch fraction',
                  minimum: 0,
                  maximum: 1,
                ),
                _numberField(
                  'minimum_distance_km',
                  'Minimum distance (km)',
                  minimum: 0,
                ),
              ],
            ),
            _section(
              'Advanced scoring',
              'Validation, precision, and GAP options',
              [
                _numberField(
                  'day_quality_override',
                  'Day quality override',
                  minimum: 0,
                  maximum: 1,
                ),
                _numberField(
                  'time_points_if_not_in_goal',
                  'Time points if not in goal',
                  minimum: 0,
                  maximum: 1,
                ),
                _numberField(
                  'min_time_span_for_valid_task_minutes',
                  'Minimum valid task span (minutes)',
                  integer: true,
                  minimum: 0,
                ),
                _numberField(
                  'leading_weight_factor',
                  'Leading weight factor',
                  minimum: 0,
                ),
                _numberField(
                  'turnpoint_radius_tolerance',
                  'Turnpoint radius tolerance',
                  minimum: 0,
                ),
                _numberField(
                  'turnpoint_radius_minimum_absolute_tolerance_m',
                  'Turnpoint minimum absolute tolerance (m)',
                  minimum: 0,
                ),
                _numberField(
                  'number_of_decimals_task_results',
                  'Task result decimals',
                  integer: true,
                  minimum: 0,
                  maximum: 6,
                ),
                _numberField(
                  'number_of_decimals_competition_results',
                  'Competition result decimals',
                  integer: true,
                  minimum: 0,
                  maximum: 6,
                ),
                _dropdown(
                  'scoring_altitude',
                  'Scoring altitude',
                  const [
                    DropdownMenuItem(value: 'GPS', child: Text('GPS altitude')),
                    DropdownMenuItem(value: 'QNH', child: Text('QNH altitude')),
                    DropdownMenuItem(
                      value: 'pressure',
                      child: Text('Pressure altitude'),
                    ),
                  ],
                ),
                _dropdown(
                  'final_glide_decelerator',
                  'Final glide decelerator',
                  const [
                    DropdownMenuItem(value: 'none', child: Text('None')),
                    DropdownMenuItem(
                      value: 'default',
                      child: Text('Default decelerator'),
                    ),
                    DropdownMenuItem(
                      value: 'stopped_task',
                      child: Text('Stopped-task decelerator'),
                    ),
                  ],
                ),
                _textField(
                  'no_final_glide_decelerator_reason',
                  'No final glide decelerator reason',
                  hint: 'Optional override note',
                ),
                _switch(
                  'use_1000_points_for_max_day_quality',
                  'Use 1000 points for max day quality',
                ),
                _switch(
                  'normalize_1000_before_day_quality',
                  'Normalize 1000 before day quality',
                ),
                _switch(
                  'use_difficulty_for_distance_points',
                  'Use difficulty for distance points',
                ),
                _switch(
                  'use_distance_squared_for_lc',
                  'Use distance squared for LC',
                ),
                _switch(
                  'use_semi_circle_control_zone_for_goal_line',
                  'Use semi-circle goal line control zone',
                ),
                _switch(
                  'use_proportional_leading_weight_if_nobody_in_goal',
                  'Use proportional leading weight if nobody is in goal',
                ),
                _switch(
                  'redistribute_removed_time_points_as_distance_points',
                  'Redistribute removed time points as distance points',
                ),
                _switch(
                  'use_best_score_for_ftv_validity',
                  'Use best score for FTV validity',
                ),
                _switch('use_constant_leading_weight',
                    'Use constant leading weight'),
                _switch('use_pwca2019_for_lc', 'Use PWCA 2019 for LC'),
                _switch(
                  'use_flat_decline_of_timepoints',
                  'Use flat decline of time points',
                ),
              ],
            ),
            _section(
              'Airspace display',
              'Visible classes and restricted fields',
              [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'Visible airspace classes',
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: _airspaceClasses.map((value) {
                    return FilterChip(
                      label: Text(value),
                      selected: selectedAirspaceClasses.contains(value),
                      onSelected: (selected) {
                        setState(() {
                          if (selected) {
                            selectedAirspaceClasses.add(value);
                          } else {
                            selectedAirspaceClasses.remove(value);
                          }
                          _settings['visible_airspace_classes_json'] =
                              _airspaceClasses
                                  .where(selectedAirspaceClasses.contains)
                                  .toList();
                        });
                      },
                    );
                  }).toList(),
                ),
                _switch('show_restricted_fields', 'Show restricted fields'),
              ],
            ),
            const SizedBox(height: 8),
            FilledButton.icon(
              key: const Key('save-event-button'),
              onPressed: _saving ? null : _save,
              icon: _saving
                  ? const SizedBox.square(
                      dimension: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.save_outlined),
              label: Text(_saving
                  ? 'Saving...'
                  : _isNew
                      ? 'Create event'
                      : 'Save event'),
            ),
          ],
        ),
      ),
    );
  }
}

class EventTaskBuilderScreen extends StatefulWidget {
  final ApiService api;
  final EventSummary event;
  final bool canEdit;

  const EventTaskBuilderScreen({
    super.key,
    required this.api,
    required this.event,
    required this.canEdit,
  });

  @override
  State<EventTaskBuilderScreen> createState() => _EventTaskBuilderScreenState();
}

class _EventTaskBuilderScreenState extends State<EventTaskBuilderScreen> {
  final MapController _mapController = MapController();
  late EventSummary _event;
  LiveMapStyle _mapStyle = LiveMapStyle.map;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  EventTask? _task;
  List<EventTask> _tasks = [];
  List<TurnpointSourceSummary> _sources = [];
  int? _sourceId;
  List<EventWaypoint> _waypoints = [];
  bool get _canEdit => widget.canEdit;

  @override
  void initState() {
    super.initState();
    _event = widget.event;
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final responses = await Future.wait([
        widget.api.getList(ApiConfig.eventTasksPath(_event.id)),
        widget.api.getList(ApiConfig.eventTurnpointSourcesPath(_event.id)),
      ]);
      final tasks = responses[0]
          .whereType<Map<String, dynamic>>()
          .map(EventTask.fromJson)
          .toList();
      final sources = responses[1]
          .whereType<Map<String, dynamic>>()
          .map(TurnpointSourceSummary.fromJson)
          .toList();
      final task = tasks.isNotEmpty
          ? tasks.first
          : (_canEdit ? _newDraft(tasks.length) : null);
      setState(() {
        _tasks = tasks;
        _task = task;
        _sources = sources;
        _sourceId = sources.isNotEmpty ? sources.first.id : null;
      });
      if (_sourceId != null) await _loadWaypoints(_sourceId!);
    } catch (error) {
      setState(() => _error = 'Could not load event tasks.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  EventTask _newDraft(int taskCount) => EventTask(
        name: 'Task ${taskCount + 1}',
        taskDate: _event.startsOn,
        taskType: 'race_to_goal_with_gates',
        status: 'draft',
        startGateCount: 1,
      );

  void _selectTask(int taskId) {
    for (final task in _tasks) {
      if (task.id == taskId) {
        setState(() => _task = task);
        return;
      }
    }
  }

  void _createDraft() {
    if (!_canEdit) return;
    setState(() {
      _task = _newDraft(_tasks.length);
      _error = null;
    });
  }

  Future<void> _loadWaypoints(int sourceId) async {
    final rows = await widget.api.getList(
      ApiConfig.eventTurnpointSourcePointsPath(_event.id, sourceId),
    );
    final waypoints = rows
        .whereType<Map<String, dynamic>>()
        .map(EventWaypoint.fromJson)
        .toList();
    setState(() {
      _sourceId = sourceId;
      _waypoints = waypoints;
    });
  }

  void _addWaypoint(EventWaypoint waypoint) {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    if (task.points.any((point) => point.turnpointId == waypoint.id)) return;
    setState(() {
      _task = task.copyWith(points: [
        ...task.points,
        EventTaskPoint.fromWaypoint(waypoint, task.points.length),
      ]);
    });
  }

  void _updatePoint(int index, EventTaskPoint point) {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    final points = [...task.points];
    points[index] = point;
    setState(() => _task = task.copyWith(points: points));
  }

  void _movePoint(int index, int delta) {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    final nextIndex = index + delta;
    if (nextIndex < 0 || nextIndex >= task.points.length) return;
    final points = [...task.points];
    final point = points.removeAt(index);
    points.insert(nextIndex, point);
    setState(() => _task = task.copyWith(points: points));
  }

  void _removePoint(int index) {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    final points = [...task.points]..removeAt(index);
    setState(() => _task = task.copyWith(points: points));
  }

  Future<void> _saveTask() async {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    if (_sourceId == null) {
      setState(() => _error = 'Select a waypoint file before saving.');
      return;
    }
    if (task.points.isEmpty) {
      setState(() => _error = 'Add at least one waypoint before saving.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final payload = task.toPayload();
      final saved = task.id == null
          ? await widget.api.post(
              ApiConfig.eventTasksPath(_event.id),
              body: payload,
            )
          : await widget.api.put(ApiConfig.taskPath(task.id!), body: payload);
      final savedTask = EventTask.fromJson(saved);
      setState(() {
        _task = savedTask;
        final index =
            _tasks.indexWhere((existing) => existing.id == savedTask.id);
        if (index >= 0) {
          _tasks = [..._tasks]..[index] = savedTask;
        } else {
          _tasks = [..._tasks, savedTask];
        }
      });
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Task saved')),
      );
    } catch (error) {
      setState(() => _error = 'Could not save task.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  LatLng get _center {
    if (_task?.points.isNotEmpty == true) {
      final point = _task!.points.first;
      return LatLng(point.latitude, point.longitude);
    }
    if (_waypoints.isNotEmpty) {
      final waypoint = _waypoints.first;
      return LatLng(waypoint.latitude, waypoint.longitude);
    }
    return const LatLng(39.5, -98.35);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final task = _task;
    final taskRoute = task?.points
            .map((point) => LatLng(point.latitude, point.longitude))
            .toList() ??
        const <LatLng>[];

    return Scaffold(
      appBar: AppBar(
        title: Text(_event.name),
        actions: _canEdit
            ? [
                IconButton(
                  onPressed: _saving
                      ? null
                      : () async {
                          final saved =
                              await Navigator.of(context).push<EventSummary>(
                            MaterialPageRoute(
                              builder: (_) => EventEditorScreen(
                                api: widget.api,
                                event: _event,
                              ),
                            ),
                          );
                          if (saved != null && mounted) {
                            setState(() => _event = saved);
                          }
                        },
                  icon: const Icon(Icons.settings_outlined),
                  tooltip: 'Event settings',
                ),
                IconButton(
                  onPressed: _saving ? null : _saveTask,
                  icon: const Icon(Icons.save_outlined),
                  tooltip: 'Save task',
                ),
              ]
            : null,
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.all(12),
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<int>(
                              key: ValueKey(task?.id ?? 'draft'),
                              initialValue: task?.id,
                              decoration:
                                  const InputDecoration(labelText: 'Task'),
                              hint: Text(task?.id == null
                                  ? task?.name ?? 'No tasks'
                                  : 'Select task'),
                              items: _tasks
                                  .where((item) => item.id != null)
                                  .map((item) => DropdownMenuItem(
                                        value: item.id,
                                        child: Text(item.name),
                                      ))
                                  .toList(),
                              onChanged: (value) {
                                if (value != null) _selectTask(value);
                              },
                            ),
                          ),
                          if (_canEdit) ...[
                            const SizedBox(width: 8),
                            OutlinedButton.icon(
                              onPressed: _saving ? null : _createDraft,
                              icon: const Icon(Icons.add),
                              label: const Text('New task'),
                            ),
                          ],
                        ],
                      ),
                      const SizedBox(height: 8),
                      if (_sources.isEmpty)
                        Text(
                          'No waypoint file is attached to this event yet.',
                          style: TextStyle(color: theme.colorScheme.error),
                        )
                      else
                        DropdownButtonFormField<int>(
                          initialValue: _sourceId,
                          decoration:
                              const InputDecoration(labelText: 'Waypoint file'),
                          items: _sources
                              .map((source) => DropdownMenuItem(
                                    value: source.id,
                                    child: Text(
                                        '${source.filename} (${source.turnpointCount})'),
                                  ))
                              .toList(),
                          onChanged: (value) {
                            if (value != null) _loadWaypoints(value);
                          },
                        ),
                      if (_error != null) ...[
                        const SizedBox(height: 8),
                        Text(_error!,
                            style: TextStyle(color: theme.colorScheme.error)),
                      ],
                    ],
                  ),
                ),
                Expanded(
                  child: Stack(
                    children: [
                      FlutterMap(
                        mapController: _mapController,
                        options: MapOptions(
                          initialCenter: _center,
                          initialZoom: _waypoints.isEmpty ? 4 : 11,
                        ),
                        children: [
                          TileLayer(
                            urlTemplate: _mapStyle.urlTemplate,
                            maxZoom: _mapStyle.maxZoom,
                            userAgentPackageName: 'com.aervyx.aervyx_mobile',
                          ),
                          if (taskRoute.length > 1)
                            PolylineLayer(
                              polylines: [
                                Polyline(
                                  points: taskRoute,
                                  strokeWidth: 3,
                                  color: Colors.deepOrange,
                                ),
                              ],
                            ),
                          if (task != null && task.points.isNotEmpty)
                            CircleLayer(
                              circles: task.points
                                  .map((point) => CircleMarker(
                                        point: LatLng(
                                            point.latitude, point.longitude),
                                        radius: point.radiusMeters,
                                        useRadiusInMeter: true,
                                        color: Colors.deepOrange.withAlpha(35),
                                        borderColor: Colors.deepOrange,
                                        borderStrokeWidth: 2,
                                      ))
                                  .toList(),
                            ),
                          MarkerLayer(
                            markers: [
                              ..._waypoints.map(
                                (waypoint) => Marker(
                                  point: LatLng(
                                      waypoint.latitude, waypoint.longitude),
                                  width: 38,
                                  height: 38,
                                  child: GestureDetector(
                                    onTap: () => _addWaypoint(waypoint),
                                    child: const Icon(
                                      Icons.place,
                                      color: Colors.blue,
                                      size: 32,
                                    ),
                                  ),
                                ),
                              ),
                              if (task != null)
                                ...task.points.asMap().entries.map(
                                      (entry) => Marker(
                                        point: LatLng(entry.value.latitude,
                                            entry.value.longitude),
                                        width: 42,
                                        height: 42,
                                        child: _NumberedTaskMarker(
                                          index: entry.key + 1,
                                        ),
                                      ),
                                    ),
                            ],
                          ),
                          const AppMapScaleBar(
                            padding: EdgeInsets.only(left: 16, bottom: 16),
                          ),
                        ],
                      ),
                      Positioned(
                        right: 12,
                        top: 12,
                        child: LiveMapStyleDropdown(
                          value: _mapStyle,
                          onChanged: (value) =>
                              setState(() => _mapStyle = value),
                        ),
                      ),
                    ],
                  ),
                ),
                if (task != null)
                  SafeArea(
                    top: false,
                    child: _TaskPointEditor(
                      points: task.points,
                      saving: _saving,
                      editable: _canEdit,
                      onChanged: _updatePoint,
                      onMove: _movePoint,
                      onRemove: _removePoint,
                      onSave: _saveTask,
                    ),
                  ),
              ],
            ),
    );
  }
}

class _NumberedTaskMarker extends StatelessWidget {
  final int index;

  const _NumberedTaskMarker({required this.index});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.deepOrange,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2),
        boxShadow: [
          BoxShadow(color: Colors.black.withAlpha(70), blurRadius: 4)
        ],
      ),
      alignment: Alignment.center,
      child: Text(
        '$index',
        style: const TextStyle(
          color: Colors.white,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }
}

class _TaskPointEditor extends StatelessWidget {
  final List<EventTaskPoint> points;
  final bool saving;
  final bool editable;
  final void Function(int index, EventTaskPoint point) onChanged;
  final void Function(int index, int delta) onMove;
  final void Function(int index) onRemove;
  final VoidCallback onSave;

  const _TaskPointEditor({
    required this.points,
    required this.saving,
    required this.editable,
    required this.onChanged,
    required this.onMove,
    required this.onRemove,
    required this.onSave,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Material(
      elevation: 8,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 300),
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 10, 16, 6),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      editable ? 'Task waypoints' : 'Task route',
                      style: theme.textTheme.titleMedium,
                    ),
                  ),
                  if (editable)
                    FilledButton.icon(
                      onPressed: saving ? null : onSave,
                      icon: const Icon(Icons.save_outlined),
                      label: Text(saving ? 'Saving...' : 'Save'),
                    ),
                ],
              ),
            ),
            const Divider(height: 1),
            Expanded(
              child: points.isEmpty
                  ? Center(
                      child: Text(editable
                          ? 'Tap waypoint markers on the map to add them.'
                          : 'No task waypoints yet.'))
                  : ListView.builder(
                      itemCount: points.length,
                      itemBuilder: (context, index) {
                        final point = points[index];
                        if (!editable) {
                          return ListTile(
                            leading: CircleAvatar(child: Text('${index + 1}')),
                            title: Text(point.name),
                            subtitle: Text(
                                '${point.pointType} - ${point.radiusMeters.round()} m'),
                          );
                        }
                        return ExpansionTile(
                          key: ValueKey('${point.turnpointId}-$index'),
                          leading: CircleAvatar(child: Text('${index + 1}')),
                          title: Text(point.name),
                          subtitle: Text(
                              '${point.pointType} - ${point.radiusMeters.round()} m'),
                          childrenPadding:
                              const EdgeInsets.fromLTRB(16, 0, 16, 12),
                          children: [
                            DropdownButtonFormField<String>(
                              initialValue: point.pointType,
                              decoration:
                                  const InputDecoration(labelText: 'Type'),
                              items: const [
                                DropdownMenuItem(
                                    value: 'start', child: Text('Start')),
                                DropdownMenuItem(
                                    value: 'turnpoint',
                                    child: Text('Turnpoint')),
                                DropdownMenuItem(
                                    value: 'ess', child: Text('ESS')),
                                DropdownMenuItem(
                                    value: 'goal', child: Text('Goal')),
                              ],
                              onChanged: (value) {
                                if (value != null) {
                                  onChanged(
                                      index, point.copyWith(pointType: value));
                                }
                              },
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                Expanded(
                                  child: DropdownButtonFormField<String>(
                                    initialValue: point.direction,
                                    decoration: const InputDecoration(
                                        labelText: 'Direction'),
                                    items: const [
                                      DropdownMenuItem(
                                          value: 'enter', child: Text('Enter')),
                                      DropdownMenuItem(
                                          value: 'exit', child: Text('Exit')),
                                    ],
                                    onChanged: (value) {
                                      if (value != null) {
                                        onChanged(index,
                                            point.copyWith(direction: value));
                                      }
                                    },
                                  ),
                                ),
                                const SizedBox(width: 12),
                                Expanded(
                                  child: TextFormField(
                                    initialValue:
                                        point.radiusMeters.round().toString(),
                                    keyboardType: TextInputType.number,
                                    decoration: const InputDecoration(
                                        labelText: 'Radius m'),
                                    onFieldSubmitted: (value) {
                                      final parsed = double.tryParse(value);
                                      if (parsed != null && parsed > 0) {
                                        onChanged(
                                            index,
                                            point.copyWith(
                                                radiusMeters: parsed));
                                      }
                                    },
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 8),
                            Row(
                              children: [
                                IconButton(
                                  onPressed: index == 0
                                      ? null
                                      : () => onMove(index, -1),
                                  icon: const Icon(Icons.arrow_upward),
                                ),
                                IconButton(
                                  onPressed: index == points.length - 1
                                      ? null
                                      : () => onMove(index, 1),
                                  icon: const Icon(Icons.arrow_downward),
                                ),
                                const Spacer(),
                                TextButton.icon(
                                  onPressed: () => onRemove(index),
                                  icon: const Icon(Icons.delete_outline),
                                  label: const Text('Remove'),
                                ),
                              ],
                            ),
                          ],
                        );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
