import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';
import '../widgets/live_map_style.dart';
import '../widgets/map_scale_bar.dart';

class ChallengeSummary {
  final int id;
  final String name;
  final String startsOn;
  final String endsOn;
  final int pilotCount;
  final String challengeType;
  final bool canEdit;

  ChallengeSummary({
    required this.id,
    required this.name,
    required this.startsOn,
    required this.endsOn,
    required this.pilotCount,
    required this.challengeType,
    required this.canEdit,
  });

  factory ChallengeSummary.fromJson(Map<String, dynamic> json) {
    return ChallengeSummary(
      id: json['id'] as int,
      name: json['name'] as String? ?? 'Challenge',
      startsOn: json['starts_on'] as String? ?? '',
      endsOn: json['ends_on'] as String? ?? '',
      pilotCount: json['pilot_count'] as int? ?? 0,
      challengeType: json['challenge_type'] as String? ?? 'open_distance',
      canEdit: json['can_edit'] as bool? ?? false,
    );
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

class ChallengeWaypoint {
  final int id;
  final String name;
  final double latitude;
  final double longitude;

  const ChallengeWaypoint({
    required this.id,
    required this.name,
    required this.latitude,
    required this.longitude,
  });

  factory ChallengeWaypoint.fromJson(Map<String, dynamic> json) {
    return ChallengeWaypoint(
      id: json['id'] as int,
      name: json['name'] as String? ?? 'Waypoint',
      latitude: (json['latitude'] as num).toDouble(),
      longitude: (json['longitude'] as num).toDouble(),
    );
  }
}

class ChallengeTask {
  final int? id;
  final String name;
  final String taskDate;
  final String taskType;
  final String status;
  final int startGateCount;
  final int? startGateIntervalSeconds;
  final List<ChallengeTaskPoint> points;

  const ChallengeTask({
    this.id,
    required this.name,
    required this.taskDate,
    required this.taskType,
    this.status = 'draft',
    this.startGateCount = 1,
    this.startGateIntervalSeconds,
    this.points = const [],
  });

  factory ChallengeTask.fromJson(Map<String, dynamic> json) {
    return ChallengeTask(
      id: json['id'] as int?,
      name: json['name'] as String? ?? 'Task',
      taskDate: json['task_date'] as String? ?? '',
      taskType: json['task_type'] as String? ?? 'open_distance',
      status: json['status'] as String? ?? 'draft',
      startGateCount: json['start_gate_count'] as int? ?? 1,
      startGateIntervalSeconds: json['start_gate_interval_seconds'] as int?,
      points: (json['points'] as List<dynamic>? ?? const [])
          .map((item) =>
              ChallengeTaskPoint.fromJson(item as Map<String, dynamic>))
          .toList(),
    );
  }

  ChallengeTask copyWith({
    String? name,
    String? taskDate,
    String? taskType,
    int? startGateCount,
    int? startGateIntervalSeconds,
    List<ChallengeTaskPoint>? points,
  }) {
    return ChallengeTask(
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

class ChallengeTaskPoint {
  final int turnpointId;
  final String name;
  final double latitude;
  final double longitude;
  final String pointType;
  final String direction;
  final double radiusMeters;

  const ChallengeTaskPoint({
    required this.turnpointId,
    required this.name,
    required this.latitude,
    required this.longitude,
    required this.pointType,
    required this.direction,
    required this.radiusMeters,
  });

  factory ChallengeTaskPoint.fromWaypoint(
    ChallengeWaypoint waypoint,
    int index,
  ) {
    final type = index == 0 ? 'start' : 'turnpoint';
    return ChallengeTaskPoint(
      turnpointId: waypoint.id,
      name: waypoint.name,
      latitude: waypoint.latitude,
      longitude: waypoint.longitude,
      pointType: type,
      direction: type == 'start' ? 'exit' : 'enter',
      radiusMeters: defaultRadiusForPointType(type),
    );
  }

  factory ChallengeTaskPoint.fromJson(Map<String, dynamic> json) {
    final type = json['point_type'] as String? ?? 'turnpoint';
    return ChallengeTaskPoint(
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

  ChallengeTaskPoint copyWith({
    String? pointType,
    String? direction,
    double? radiusMeters,
  }) {
    final nextType = pointType ?? this.pointType;
    return ChallengeTaskPoint(
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

class ChallengesScreen extends StatefulWidget {
  final ApiService api;

  const ChallengesScreen({super.key, required this.api});

  @override
  State<ChallengesScreen> createState() => _ChallengesScreenState();
}

class _ChallengesScreenState extends State<ChallengesScreen> {
  final _nameController = TextEditingController(text: 'New XC Challenge');
  final _locationController = TextEditingController();
  DateTime _startsOn = DateTime.now();
  DateTime _endsOn = DateTime.now();
  String _challengeType = 'open_distance';
  bool _publicTracking = false;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  List<ChallengeSummary> _challenges = [];

  @override
  void initState() {
    super.initState();
    _loadChallenges();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _locationController.dispose();
    super.dispose();
  }

  Future<void> _loadChallenges() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await widget.api.getList(ApiConfig.challengesPath);
      setState(() {
        _challenges = rows
            .whereType<Map<String, dynamic>>()
            .map(ChallengeSummary.fromJson)
            .toList();
      });
    } catch (error) {
      setState(() => _error = 'Could not load challenges.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _pickDate({required bool start}) async {
    final initial = start ? _startsOn : _endsOn;
    final picked = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: DateTime.now().subtract(const Duration(days: 1)),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (picked == null) return;
    setState(() {
      if (start) {
        _startsOn = picked;
        if (_endsOn.isBefore(_startsOn)) _endsOn = picked;
      } else {
        _endsOn = picked;
      }
    });
  }

  Future<void> _createChallenge() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final created = await widget.api.post(ApiConfig.challengesPath, body: {
        'name': name,
        'challenge_type': _challengeType,
        'starts_on': _dateString(_startsOn),
        'ends_on': _dateString(_endsOn),
        'location': _locationController.text.trim(),
        'visibility': 'public',
        'public_listed': false,
        'is_public_tracking': _publicTracking,
      });
      _nameController.text = _challengeType == 'open_distance'
          ? 'New XC Challenge'
          : 'New R2G Challenge';
      _locationController.clear();
      await _loadChallenges();
      if (!mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(
        builder: (_) => ChallengeTaskBuilderScreen(
          api: widget.api,
          challenge: ChallengeSummary.fromJson(created),
        ),
      ));
      await _loadChallenges();
    } catch (error) {
      setState(() => _error = 'Could not create challenge.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  String _dateString(DateTime value) {
    final local = DateTime(value.year, value.month, value.day);
    return local.toIso8601String().substring(0, 10);
  }

  Widget _createChallengeCard(ThemeData theme) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Create challenge', style: theme.textTheme.titleMedium),
            const SizedBox(height: 12),
            TextField(
              controller: _nameController,
              decoration: const InputDecoration(labelText: 'Name'),
            ),
            const SizedBox(height: 12),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'open_distance', label: Text('XC')),
                ButtonSegment(
                    value: 'race_to_goal_with_gates', label: Text('R2G')),
              ],
              selected: {_challengeType},
              onSelectionChanged: (value) {
                setState(() => _challengeType = value.first);
              },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _locationController,
              decoration: const InputDecoration(labelText: 'Location'),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _pickDate(start: true),
                    child: Text('Starts ${_dateString(_startsOn)}'),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => _pickDate(start: false),
                    child: Text('Ends ${_dateString(_endsOn)}'),
                  ),
                ),
              ],
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              value: _publicTracking,
              onChanged: (value) => setState(() => _publicTracking = value),
              title: const Text('Public live tracking'),
            ),
            FilledButton.icon(
              onPressed: _saving ? null : _createChallenge,
              icon: const Icon(Icons.add),
              label: Text(_saving ? 'Creating...' : 'Create and build task'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
            ],
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Challenges')),
      body: RefreshIndicator(
        onRefresh: _loadChallenges,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text('My challenges', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loading)
              const Center(
                  child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(),
              ))
            else if (_challenges.isEmpty)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text('No challenges yet.'),
              )
            else
              ..._challenges.map((challenge) => Card(
                    child: ListTile(
                      leading: const Icon(Icons.emoji_events_outlined),
                      title: Text(challenge.name),
                      subtitle:
                          Text('${challenge.startsOn} - ${challenge.endsOn}'),
                      trailing: Text('${challenge.pilotCount} pilots'),
                      onTap: () async {
                        await Navigator.of(context).push(MaterialPageRoute(
                          builder: (_) => ChallengeTaskBuilderScreen(
                            api: widget.api,
                            challenge: challenge,
                          ),
                        ));
                        await _loadChallenges();
                      },
                    ),
                  )),
            const SizedBox(height: 16),
            _createChallengeCard(theme),
          ],
        ),
      ),
    );
  }
}

class ChallengeTaskBuilderScreen extends StatefulWidget {
  final ApiService api;
  final ChallengeSummary challenge;

  const ChallengeTaskBuilderScreen({
    super.key,
    required this.api,
    required this.challenge,
  });

  @override
  State<ChallengeTaskBuilderScreen> createState() =>
      _ChallengeTaskBuilderScreenState();
}

class _ChallengeTaskBuilderScreenState
    extends State<ChallengeTaskBuilderScreen> {
  final MapController _mapController = MapController();
  LiveMapStyle _mapStyle = LiveMapStyle.map;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  ChallengeTask? _task;
  List<TurnpointSourceSummary> _sources = [];
  int? _sourceId;
  List<ChallengeWaypoint> _waypoints = [];
  bool get _canEdit => widget.challenge.canEdit;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final responses = await Future.wait([
        widget.api.getList(ApiConfig.challengeTasksPath(widget.challenge.id)),
        widget.api
            .getList(ApiConfig.eventTurnpointSourcesPath(widget.challenge.id)),
      ]);
      final tasks = responses[0]
          .whereType<Map<String, dynamic>>()
          .map(ChallengeTask.fromJson)
          .toList();
      final sources = responses[1]
          .whereType<Map<String, dynamic>>()
          .map(TurnpointSourceSummary.fromJson)
          .toList();
      final task = tasks.isNotEmpty
          ? tasks.first
          : ChallengeTask(
              name: widget.challenge.name,
              taskDate: widget.challenge.startsOn,
              taskType: widget.challenge.challengeType,
              startGateCount: 1,
            );
      setState(() {
        _task = task;
        _sources = sources;
        _sourceId = sources.isNotEmpty ? sources.first.id : null;
      });
      if (_sourceId != null) await _loadWaypoints(_sourceId!);
    } catch (error) {
      setState(() => _error = 'Could not load challenge task.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _loadWaypoints(int sourceId) async {
    final rows = await widget.api.getList(
      ApiConfig.eventTurnpointSourcePointsPath(widget.challenge.id, sourceId),
    );
    final waypoints = rows
        .whereType<Map<String, dynamic>>()
        .map(ChallengeWaypoint.fromJson)
        .toList();
    setState(() {
      _sourceId = sourceId;
      _waypoints = waypoints;
    });
  }

  void _addWaypoint(ChallengeWaypoint waypoint) {
    if (!_canEdit) return;
    final task = _task;
    if (task == null) return;
    if (task.points.any((point) => point.turnpointId == waypoint.id)) return;
    setState(() {
      _task = task.copyWith(points: [
        ...task.points,
        ChallengeTaskPoint.fromWaypoint(waypoint, task.points.length),
      ]);
    });
  }

  void _updatePoint(int index, ChallengeTaskPoint point) {
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
              ApiConfig.challengeTasksPath(widget.challenge.id),
              body: payload,
            )
          : await widget.api.put(ApiConfig.taskPath(task.id!), body: payload);
      setState(() => _task = ChallengeTask.fromJson(saved));
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
        title: Text(widget.challenge.name),
        actions: _canEdit
            ? [
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
                      if (_sources.isEmpty)
                        Text(
                          'No waypoint file is attached to this challenge yet.',
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
  final List<ChallengeTaskPoint> points;
  final bool saving;
  final bool editable;
  final void Function(int index, ChallengeTaskPoint point) onChanged;
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
