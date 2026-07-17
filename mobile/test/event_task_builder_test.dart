import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/screens/events_screen.dart';
import 'package:aervyx_mobile/services/api_service.dart';

class FakeEventApi extends ApiService {
  @override
  Future<List<dynamic>> getList(String path,
      {Map<String, String>? query}) async {
    if (path == ApiConfig.eventsPath) {
      return [
        {
          'id': 7,
          'name': 'Spring Event',
          'starts_on': '2026-06-26',
          'ends_on': '2026-06-27',
        }
      ];
    }
    if (path == ApiConfig.eventTasksPath(7)) {
      return [
        _task(70, 'Task 1', 'START'),
        _task(71, 'Task 2', 'GOAL'),
      ];
    }
    if (path == ApiConfig.eventTurnpointSourcesPath(7)) {
      return [
        {'id': 9, 'filename': 'Waypoints.gpx', 'turnpoint_count': 2}
      ];
    }
    if (path == ApiConfig.eventTurnpointSourcePointsPath(7, 9)) {
      return [
        {'id': 42, 'name': 'START', 'latitude': 39.1, 'longitude': -105.2},
        {'id': 43, 'name': 'GOAL', 'latitude': 39.2, 'longitude': -105.1},
      ];
    }
    return [];
  }

  Map<String, dynamic> _task(int id, String name, String pointName) => {
        'id': id,
        'name': name,
        'task_date': '2026-06-26',
        'task_type': 'race_to_goal_with_gates',
        'status': 'draft',
        'start_gate_count': 1,
        'points': [
          {
            'turnpoint_id': pointName == 'START' ? 42 : 43,
            'name': pointName,
            'latitude': pointName == 'START' ? 39.1 : 39.2,
            'longitude': pointName == 'START' ? -105.2 : -105.1,
            'point_type': pointName == 'START' ? 'start' : 'goal',
            'direction': pointName == 'START' ? 'exit' : 'enter',
            'radius_m': pointName == 'START' ? 5000 : 400,
          }
        ],
      };
}

const event = EventSummary(
  id: 7,
  name: 'Spring Event',
  startsOn: '2026-06-26',
  endsOn: '2026-06-27',
);

void main() {
  test('event task payload uses selected waypoint ids and draft defaults', () {
    const waypoint = EventWaypoint(
      id: 42,
      name: 'START',
      latitude: 39.1,
      longitude: -105.2,
    );
    final task = EventTask(
      name: 'Task 1',
      taskDate: event.startsOn,
      taskType: 'race_to_goal_with_gates',
      status: 'draft',
      points: [EventTaskPoint.fromWaypoint(waypoint, 0)],
    );

    final payload = task.toPayload();
    final point =
        (payload['points'] as List<dynamic>).single as Map<String, dynamic>;

    expect(payload['name'], 'Task 1');
    expect(payload['task_date'], '2026-06-26');
    expect(payload['task_type'], 'race_to_goal_with_gates');
    expect(payload['status'], 'draft');
    expect(point['turnpoint_id'], 42);
    expect(point['point_type'], 'start');
    expect(point['direction'], 'exit');
    expect(point['radius_m'], 5000);
  });

  testWidgets('event list loads accessible events without a create form',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: EventsScreen(api: FakeEventApi()),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Events'), findsNWidgets(2));
    expect(find.text('Spring Event'), findsOneWidget);
    expect(find.textContaining('Create'), findsNothing);
  });

  testWidgets('task selector switches between every event task',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: EventTaskBuilderScreen(
        api: FakeEventApi(),
        event: event,
        canEdit: false,
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.text('START'), findsWidgets);
    await tester.tap(find.byType(DropdownButtonFormField<int>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Task 2').last);
    await tester.pumpAndSettle();
    expect(find.text('GOAL'), findsWidgets);
  });

  testWidgets('staff can start a numbered draft', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: EventTaskBuilderScreen(
        api: FakeEventApi(),
        event: event,
        canEdit: true,
      ),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.text('New task'));
    await tester.pump();
    expect(find.text('Task 3'), findsOneWidget);
    expect(find.byTooltip('Save task'), findsOneWidget);
  });

  testWidgets('pilot event route is read only', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: EventTaskBuilderScreen(
        api: FakeEventApi(),
        event: event,
        canEdit: false,
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byTooltip('Save task'), findsNothing);
    expect(find.text('New task'), findsNothing);
    expect(find.text('Task route'), findsOneWidget);
    expect(find.text('START'), findsWidgets);
  });
}
