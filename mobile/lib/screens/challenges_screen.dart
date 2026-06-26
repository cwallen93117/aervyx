import 'package:flutter/material.dart';

import '../config/api_config.dart';
import '../services/api_service.dart';

class ChallengeSummary {
  final int id;
  final String name;
  final String startsOn;
  final String endsOn;
  final int pilotCount;
  final String? publicSlug;

  ChallengeSummary({
    required this.id,
    required this.name,
    required this.startsOn,
    required this.endsOn,
    required this.pilotCount,
    this.publicSlug,
  });

  factory ChallengeSummary.fromJson(Map<String, dynamic> json) {
    return ChallengeSummary(
      id: json['id'] as int,
      name: json['name'] as String? ?? 'Challenge',
      startsOn: json['starts_on'] as String? ?? '',
      endsOn: json['ends_on'] as String? ?? '',
      pilotCount: json['pilot_count'] as int? ?? 0,
      publicSlug: json['public_slug'] as String?,
    );
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
      await widget.api.post(ApiConfig.challengesPath, body: {
        'name': name,
        'challenge_type': _challengeType,
        'starts_on': _dateString(_startsOn),
        'ends_on': _dateString(_endsOn),
        'location': _locationController.text.trim(),
        'visibility': 'public',
        'public_listed': false,
        'is_public_tracking': _publicTracking,
      });
      _nameController.text =
          _challengeType == 'open_distance' ? 'New XC Challenge' : 'New R2G Challenge';
      _locationController.clear();
      await _loadChallenges();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Challenge created')),
      );
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
            Card(
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
                        ButtonSegment(value: 'race_to_goal_with_gates', label: Text('R2G')),
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
                      label: Text(_saving ? 'Creating...' : 'Create'),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: 8),
                      Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
                    ],
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text('My challenges', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loading)
              const Center(child: Padding(
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
                      subtitle: Text('${challenge.startsOn} - ${challenge.endsOn}'),
                      trailing: Text('${challenge.pilotCount} pilots'),
                    ),
                  )),
          ],
        ),
      ),
    );
  }
}
