from datetime import UTC, datetime

from app.models import TaskPoint, TrackPoint
from app.services.scoring import evaluate_task


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