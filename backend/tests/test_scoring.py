from datetime import UTC, datetime

from app.models import Task, TaskPoint, TrackPoint
from app.services.scoring import _score_evaluations, evaluate_task


def _task(task_id: int = 1, nominal_time_hours: float = 1.5) -> Task:
    task = Task(
        id=task_id,
        event_id=1,
        name="Task 1",
        status="published",
        nominal_distance_km=60,
        nominal_time_hours=nominal_time_hours,
        nominal_launch=0.95,
        minimum_distance_km=5,
        penalties_json={},
    )
    return task


def _task_point(identifier: int, position: int, point_type: str, lat: float, lon: float, radius_m: float) -> TaskPoint:
    point = TaskPoint(task_id=1, position=position, point_type=point_type, radius_m=radius_m, name=point_type.title(), latitude=lat, longitude=lon)
    point.id = identifier
    return point


def _track_point(sequence: int, lat: float, lon: float) -> TrackPoint:
    point = TrackPoint(upload_id=1, sequence=sequence, recorded_at=datetime(2026, 3, 17, 12, sequence, tzinfo=UTC), latitude=lat, longitude=lon)
    point.id = sequence
    return point


def test_scoring_detects_goal_completion() -> None:
    task_points = [
        _task_point(1, 1, "launch", 36.600, -118.000, 500),
        _task_point(2, 2, "start", 36.650, -118.050, 1000),
        _task_point(3, 3, "turnpoint", 36.700, -118.100, 600),
        _task_point(4, 4, "ESS", 36.750, -118.150, 1000),
        _task_point(5, 5, "goal", 36.800, -118.200, 500),
    ]
    track_points = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.700, -118.100),
        _track_point(4, 36.750, -118.150),
        _track_point(5, 36.800, -118.200),
    ]
    result = evaluate_task(task_points, track_points)
    assert result["status"] == "goal"
    assert result["distance_flown_km"] > 0


def test_cursor_does_not_reuse_same_fix_for_next_turnpoint() -> None:
    task_points = [
        _task_point(1, 1, "launch", 36.600, -118.000, 500),
        _task_point(2, 2, "start", 36.650, -118.050, 300),
        _task_point(3, 3, "turnpoint", 36.650, -118.050, 300),
        _task_point(4, 4, "goal", 36.800, -118.200, 500),
    ]
    track_points = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.700, -118.100),
    ]
    result = evaluate_task(task_points, track_points)
    hit_flags = [hit["hit"] for hit in result["details"]["hits"]]
    assert hit_flags == [True, True, False, False]


def test_gap_breakdown_contains_airscore_style_point_buckets() -> None:
    task_points = [
        _task_point(1, 1, "launch", 36.600, -118.000, 500),
        _task_point(2, 2, "start", 36.650, -118.050, 1000),
        _task_point(3, 3, "turnpoint", 36.700, -118.100, 600),
        _task_point(4, 4, "ESS", 36.750, -118.150, 1000),
        _task_point(5, 5, "goal", 36.800, -118.200, 500),
    ]
    winning_track = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.700, -118.100),
        _track_point(4, 36.750, -118.150),
        _track_point(5, 36.800, -118.200),
    ]
    trailing_track = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.690, -118.090),
    ]
    upload_a = type("UploadStub", (), {"id": 10, "pilot_id": 1})()
    upload_b = type("UploadStub", (), {"id": 11, "pilot_id": 2})()

    scored = _score_evaluations(
        _task(nominal_time_hours=0.05),
        2,
        [
            {"upload": upload_a, "evaluation": evaluate_task(task_points, winning_track)},
            {"upload": upload_b, "evaluation": evaluate_task(task_points, trailing_track)},
        ],
    )

    assert scored[0]["pilot_id"] == 1
    assert scored[0]["score_points"] > scored[1]["score_points"]
    gap = scored[0]["details_json"]["gap"]
    assert gap["available_points"]["distance"] > 0
    assert gap["awarded_points"]["speed"] >= 0
    assert gap["validity"]["overall"] > 0
