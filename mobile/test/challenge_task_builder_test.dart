import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:aervyx_mobile/config/api_config.dart';
import 'package:aervyx_mobile/screens/challenges_screen.dart';
import 'package:aervyx_mobile/services/api_service.dart';

class FakeChallengeApi extends ApiService {
  @override
  Future<List<dynamic>> getList(String path,
      {Map<String, String>? query}) async {
    if (path == ApiConfig.challengesPath) {
      return [
        {
          'id': 7,
          'name': 'Buddy Challenge',
          'starts_on': '2026-06-26',
          'ends_on': '2026-06-27',
          'pilot_count': 2,
          'challenge_type': 'open_distance',
          'can_edit': false,
        }
      ];
    }
    if (path == ApiConfig.challengeTasksPath(7)) {
      return [
        {
          'id': 70,
          'name': 'Task',
          'task_date': '2026-06-26',
          'task_type': 'open_distance',
          'status': 'draft',
          'start_gate_count': 1,
          'points': [
            {
              'turnpoint_id': 42,
              'name': 'START',
              'latitude': 39.1,
              'longitude': -105.2,
              'point_type': 'start',
              'direction': 'exit',
              'radius_m': 5000,
            }
          ],
        }
      ];
    }
    if (path == ApiConfig.eventTurnpointSourcesPath(7)) {
      return [
        {'id': 9, 'filename': 'Waypoints.gpx', 'turnpoint_count': 1}
      ];
    }
    if (path == ApiConfig.eventTurnpointSourcePointsPath(7, 9)) {
      return [
        {'id': 42, 'name': 'START', 'latitude': 39.1, 'longitude': -105.2}
      ];
    }
    return [];
  }
}

void main() {
  test('challenge summary parses edit permission', () {
    final challenge = ChallengeSummary.fromJson({
      'id': 1,
      'name': 'Owner Challenge',
      'can_edit': true,
    });

    expect(challenge.canEdit, isTrue);
  });

  test('challenge task payload uses selected waypoint ids', () {
    const waypoint = ChallengeWaypoint(
      id: 42,
      name: 'START',
      latitude: 39.1,
      longitude: -105.2,
    );
    final task = ChallengeTask(
      name: 'Task',
      taskDate: '2026-06-26',
      taskType: 'open_distance',
      points: [ChallengeTaskPoint.fromWaypoint(waypoint, 0)],
    );

    final payload = task.toPayload();
    final points = payload['points'] as List<dynamic>;
    final point = points.single as Map<String, dynamic>;

    expect(point['turnpoint_id'], 42);
    expect(point['name'], 'START');
    expect(point['point_type'], 'start');
    expect(point['direction'], 'exit');
    expect(point['radius_m'], 5000);
  });

  testWidgets('challenge list shows my challenges before create form',
      (tester) async {
    await tester.pumpWidget(
        MaterialApp(home: ChallengesScreen(api: FakeChallengeApi())));
    await tester.pumpAndSettle();

    expect(tester.getTopLeft(find.text('My challenges')).dy,
        lessThan(tester.getTopLeft(find.text('Create challenge')).dy));
  });

  testWidgets('readonly challenge hides edit controls', (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: ChallengeTaskBuilderScreen(
        api: FakeChallengeApi(),
        challenge: ChallengeSummary.fromJson({
          'id': 7,
          'name': 'Buddy Challenge',
          'starts_on': '2026-06-26',
          'ends_on': '2026-06-27',
          'challenge_type': 'open_distance',
          'can_edit': false,
        }),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byTooltip('Save task'), findsNothing);
    expect(find.text('Task route'), findsOneWidget);
    expect(find.text('START'), findsWidgets);
  });
}
