import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/screens/events_screen.dart';
import 'package:aervyx_mobile/services/api_service.dart';

class FakeEventApi extends ApiService {
  Map<String, dynamic>? lastPostBody;
  Map<String, dynamic>? lastPutBody;
  Map<String, dynamic>? lastPatchBody;

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
    if (path == ApiConfig.eventScoringPresetsPath(7)) return [];
    return [];
  }

  @override
  Future<Map<String, dynamic>> post(String path,
      {Map<String, dynamic>? body}) async {
    lastPostBody = body;
    return {'id': 99, ...?body};
  }

  @override
  Future<Map<String, dynamic>> put(String path,
      {Map<String, dynamic>? body}) async {
    lastPutBody = body;
    return {'id': 7, ...?body};
  }

  @override
  Future<Map<String, dynamic>> patch(String path,
      {Map<String, dynamic>? body}) async {
    lastPatchBody = body;
    return {};
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

final event = EventSummary(
  id: 7,
  name: 'Spring Event',
  startsOn: '2026-06-26',
  endsOn: '2026-06-27',
);

void main() {
  test('event payload covers every web-editable event field', () {
    final payload = EventSummary.draft(DateTime(2026, 7, 18)).toPayload();

    expect(payload.keys.toSet(), {
      'name',
      'location',
      'starts_on',
      'ends_on',
      'timezone',
      'scoring_formula',
      'nominal_distance_km',
      'nominal_time_hours',
      'nominal_launch',
      'minimum_distance_km',
      'nominal_goal_percent',
      'score_back_time_minutes',
      'goal_ss_penalty',
      'day_quality_override',
      'time_points_if_not_in_goal',
      'jump_the_gun_factor',
      'jump_the_gun_max_seconds',
      'default_start_gate_count',
      'default_start_gate_interval_seconds',
      'stopped_glide_bonus',
      'use_1000_points_for_max_day_quality',
      'normalize_1000_before_day_quality',
      'use_distance_points',
      'use_time_points',
      'use_leading_points',
      'use_arrival_position_points',
      'use_arrival_time_points',
      'use_departure_points',
      'use_difficulty_for_distance_points',
      'use_distance_squared_for_lc',
      'use_semi_circle_control_zone_for_goal_line',
      'use_proportional_leading_weight_if_nobody_in_goal',
      'redistribute_removed_time_points_as_distance_points',
      'use_best_score_for_ftv_validity',
      'use_constant_leading_weight',
      'use_pwca2019_for_lc',
      'use_flat_decline_of_timepoints',
      'scoring_altitude',
      'final_glide_decelerator',
      'no_final_glide_decelerator_reason',
      'min_time_span_for_valid_task_minutes',
      'leading_weight_factor',
      'turnpoint_radius_tolerance',
      'turnpoint_radius_minimum_absolute_tolerance_m',
      'number_of_decimals_task_results',
      'number_of_decimals_competition_results',
      'visible_airspace_classes_json',
      'show_restricted_fields',
      'penalties_json',
      'is_public_tracking',
      'visibility',
    });
    expect(payload['starts_on'], '2026-07-18');
    expect(payload['ends_on'], '2026-07-24');
  });

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

  testWidgets('staff can create an event with native date controls',
      (tester) async {
    final api = FakeEventApi();
    await tester.pumpWidget(MaterialApp(
      home: EventsScreen(api: api, canManageEvents: true),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('new-event-button')));
    await tester.pumpAndSettle();
    expect(find.text('New event'), findsOneWidget);
    expect(find.byKey(const Key('event-starts_on')), findsOneWidget);
    expect(find.byKey(const Key('event-ends_on')), findsOneWidget);

    await tester.tap(find.byKey(const Key('event-starts_on')));
    await tester.pumpAndSettle();
    expect(find.byType(CalendarDatePicker), findsOneWidget);
    await tester
        .tap(find.textContaining(RegExp('cancel', caseSensitive: false)));
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const Key('event-name')),
      'Mobile Event',
    );
    await tester.tap(find.byTooltip('Create event'));
    await tester.pumpAndSettle();

    expect(api.lastPostBody?['name'], 'Mobile Event');
    expect(api.lastPostBody?.keys.toSet(), defaultEventSettings().keys.toSet());
    expect(api.lastPatchBody, {'presets': <dynamic>[]});
  });

  testWidgets('staff can edit existing event settings', (tester) async {
    final api = FakeEventApi();
    await tester.pumpWidget(MaterialApp(
      home: EventsScreen(api: api, canManageEvents: true),
    ));
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('edit-event-7')));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byKey(const Key('event-location')),
      'Morningside',
    );
    await tester.tap(find.byTooltip('Save event'));
    await tester.pumpAndSettle();

    expect(api.lastPutBody?['location'], 'Morningside');
    expect(api.lastPutBody?['starts_on'], '2026-06-26');
  });

  testWidgets('mobile formula selection applies the web scoring preset',
      (tester) async {
    final api = FakeEventApi();
    await tester.pumpWidget(MaterialApp(
      home: EventEditorScreen(api: api, event: event),
    ));
    await tester.pumpAndSettle();

    await tester.scrollUntilVisible(
      find.text('Formula and points'),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.text('Formula and points'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('event-scoring_formula-0')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GAP2025').last);
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Save event'));
    await tester.pumpAndSettle();

    expect(api.lastPutBody?['scoring_formula'], 'GAP2025');
    expect(api.lastPutBody?['nominal_distance_km'], 50.0);
    expect(api.lastPutBody?['nominal_goal_percent'], 0.3);
    expect(api.lastPutBody?['use_leading_points'], isTrue);
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
