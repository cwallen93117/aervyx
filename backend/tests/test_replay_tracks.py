from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.models import TaskPoint
from app.services.replay_tracks import simplify_replay_points


@dataclass(frozen=True)
class Fix:
    latitude: float
    longitude: float
    recorded_at: datetime


def _fixes(count: int) -> list[Fix]:
    start = datetime(2026, 6, 1, 12, tzinfo=UTC)
    return [
        Fix(
            latitude=40.0 + index * 0.001,
            longitude=-77.0,
            recorded_at=start + timedelta(seconds=index),
        )
        for index in range(count)
    ]


def test_short_replay_track_is_not_simplified() -> None:
    points = _fixes(10)

    result = simplify_replay_points(points, max_points=20)

    assert result.points == points
    assert result.original_point_count == 10
    assert result.returned_point_count == 10
    assert result.simplified is False


def test_long_replay_track_is_reduced_and_keeps_endpoints() -> None:
    points = _fixes(1000)

    result = simplify_replay_points(points, max_points=100)

    assert result.simplified is True
    assert result.original_point_count == 1000
    assert result.returned_point_count <= 100
    assert result.points[0] == points[0]
    assert result.points[-1] == points[-1]


def test_task_detail_points_are_preserved_near_task_cylinder() -> None:
    points = _fixes(1000)
    task_point = TaskPoint(
        task_id=1,
        position=1,
        point_type="start",
        radius_m=400,
        name="Start",
        latitude=points[500].latitude,
        longitude=points[500].longitude,
    )

    result = simplify_replay_points(points, task_points=[task_point], max_points=120)

    assert result.simplified is True
    assert result.task_aware is True
    assert points[500] in result.points
    assert points[499] in result.points
    assert points[501] in result.points
