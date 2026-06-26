import 'package:flutter_test/flutter_test.dart';
import 'package:aervyx_mobile/screens/challenges_screen.dart';

void main() {
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
}
