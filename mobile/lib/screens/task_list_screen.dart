import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../config/api_config.dart';
import '../models/task.dart';
import '../services/api_service.dart';
import '../services/auth_service.dart';
import 'task_map_screen.dart';
import 'ble_pairing_screen.dart';

class TaskListScreen extends StatefulWidget {
  const TaskListScreen({super.key});

  @override
  State<TaskListScreen> createState() => _TaskListScreenState();
}

class _TaskListScreenState extends State<TaskListScreen> {
  List<Event> _events = [];
  Map<int, List<Task>> _tasksByEvent = {};
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final api = context.read<ApiService>();
      final eventsJson = await api.getList(ApiConfig.eventsPath);
      final events =
          eventsJson.map((e) => Event.fromJson(e as Map<String, dynamic>)).toList();

      final Map<int, List<Task>> tasksByEvent = {};
      for (final event in events) {
        final tasksJson = await api.getList(ApiConfig.tasksPath(event.id));
        tasksByEvent[event.id] =
            tasksJson.map((t) => Task.fromJson(t as Map<String, dynamic>)).toList();
      }

      setState(() {
        _events = events;
        _tasksByEvent = tasksByEvent;
      });
    } catch (e) {
      setState(() => _error = e.toString());
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthService>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Aervyx'),
        actions: [
          IconButton(
            icon: const Icon(Icons.bluetooth),
            tooltip: 'Meshtastic BLE',
            onPressed: () => Navigator.push(
              context,
              MaterialPageRoute(builder: (_) => const BlePairingScreen()),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Log out',
            onPressed: () => auth.logout(),
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(_error!, style: const TextStyle(color: Colors.red)),
                      const SizedBox(height: 16),
                      FilledButton(
                        onPressed: _loadData,
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadData,
                  child: _events.isEmpty
                      ? const Center(child: Text('No events found'))
                      : ListView.builder(
                          itemCount: _events.length,
                          itemBuilder: (context, index) {
                            final event = _events[index];
                            final tasks = _tasksByEvent[event.id] ?? [];
                            return _EventCard(
                              event: event,
                              tasks: tasks,
                              onTaskTap: (task) => Navigator.push(
                                context,
                                MaterialPageRoute(
                                  builder: (_) => TaskMapScreen(task: task),
                                ),
                              ),
                            );
                          },
                        ),
                ),
    );
  }
}

class _EventCard extends StatelessWidget {
  final Event event;
  final List<Task> tasks;
  final ValueChanged<Task> onTaskTap;

  const _EventCard({
    required this.event,
    required this.tasks,
    required this.onTaskTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(event.name,
                style: Theme.of(context).textTheme.titleMedium),
            Text('${event.location}  ·  ${event.startsOn} — ${event.endsOn}',
                style: Theme.of(context).textTheme.bodySmall),
            if (tasks.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 12),
                child: Text('No tasks yet',
                    style: TextStyle(color: Colors.grey)),
              )
            else
              ...tasks.map((task) => ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.flight_takeoff),
                    title: Text(task.name),
                    subtitle: Text(
                        '${task.taskType}  ·  ${task.points.length} waypoints'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () => onTaskTap(task),
                  )),
          ],
        ),
      ),
    );
  }
}
