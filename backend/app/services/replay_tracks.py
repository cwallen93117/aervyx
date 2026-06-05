from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol, Sequence

from app.models import TaskPoint

DEFAULT_REPLAY_MAX_POINTS = 12000
TASK_DETAIL_RADIUS_BUFFER_M = 1000.0
TASK_DETAIL_MIN_RADIUS_M = 1500.0
TASK_DETAIL_TIME_WINDOW_SECONDS = 90


class ReplayPoint(Protocol):
    latitude: float
    longitude: float
    recorded_at: datetime


@dataclass(frozen=True)
class ReplaySimplificationResult:
    points: list[ReplayPoint]
    original_point_count: int
    returned_point_count: int
    max_points: int
    simplified: bool
    task_aware: bool


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000.0
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    return 2 * radius_m * math.asin(min(1.0, math.sqrt(a)))


def _task_detail_radius_m(task_point: TaskPoint) -> float:
    radius_m = float(task_point.radius_m or 0)
    return max(TASK_DETAIL_MIN_RADIUS_M, radius_m + TASK_DETAIL_RADIUS_BUFFER_M)


def _critical_indexes(points: Sequence[ReplayPoint], task_points: Sequence[TaskPoint]) -> set[int]:
    if not points or not task_points:
        return set()
    direct_matches: set[int] = set()
    detail_zones = [
        (task_point.latitude, task_point.longitude, _task_detail_radius_m(task_point))
        for task_point in task_points
        if task_point.latitude is not None and task_point.longitude is not None
    ]
    for index, point in enumerate(points):
        for latitude, longitude, radius_m in detail_zones:
            if _haversine_m(point.latitude, point.longitude, latitude, longitude) <= radius_m:
                direct_matches.add(index)
                break
    if not direct_matches:
        return set()
    expanded: set[int] = set(direct_matches)
    for index in direct_matches:
        timestamp = points[index].recorded_at
        cursor = index - 1
        while cursor >= 0 and abs((timestamp - points[cursor].recorded_at).total_seconds()) <= TASK_DETAIL_TIME_WINDOW_SECONDS:
            expanded.add(cursor)
            cursor -= 1
        cursor = index + 1
        while cursor < len(points) and abs((points[cursor].recorded_at - timestamp).total_seconds()) <= TASK_DETAIL_TIME_WINDOW_SECONDS:
            expanded.add(cursor)
            cursor += 1
    return expanded


def _task_anchor_indexes(points: Sequence[ReplayPoint], task_points: Sequence[TaskPoint]) -> set[int]:
    anchors: set[int] = set()
    if not points or not task_points:
        return anchors
    for task_point in task_points:
        if task_point.latitude is None or task_point.longitude is None:
            continue
        nearest_index = min(
            range(len(points)),
            key=lambda index: _haversine_m(points[index].latitude, points[index].longitude, task_point.latitude, task_point.longitude),
        )
        anchors.update(index for index in (nearest_index - 1, nearest_index, nearest_index + 1) if 0 <= index < len(points))
    return anchors


def _sample_indexes(indexes: Iterable[int], quota: int) -> set[int]:
    ordered = sorted(set(indexes))
    if quota <= 0 or not ordered:
        return set()
    if len(ordered) <= quota:
        return set(ordered)
    stride = math.ceil(len(ordered) / quota)
    sampled = {ordered[index] for index in range(0, len(ordered), stride)}
    sampled.add(ordered[-1])
    while len(sampled) > quota:
        sampled.remove(sorted(sampled)[-2])
    return sampled


def simplify_replay_points(
    points: Sequence[ReplayPoint],
    *,
    task_points: Sequence[TaskPoint] | None = None,
    max_points: int = DEFAULT_REPLAY_MAX_POINTS,
) -> ReplaySimplificationResult:
    original_count = len(points)
    try:
        max_points = max(2, int(max_points or DEFAULT_REPLAY_MAX_POINTS))
    except (TypeError, ValueError):
        max_points = DEFAULT_REPLAY_MAX_POINTS
    if original_count <= max_points:
        return ReplaySimplificationResult(
            points=list(points),
            original_point_count=original_count,
            returned_point_count=original_count,
            max_points=max_points,
            simplified=False,
            task_aware=bool(task_points),
        )

    keep: set[int] = {0, original_count - 1}
    critical = _critical_indexes(points, task_points or [])
    keep.update(_task_anchor_indexes(points, task_points or []))
    task_aware = bool(critical)
    if len(critical) <= int(max_points * 0.8):
        keep.update(critical)
    else:
        critical_quota = max(0, min(len(critical), int(max_points * 0.65)))
        keep.update(_sample_indexes(critical, critical_quota))
    remaining_quota = max_points - len(keep)
    noncritical = (index for index in range(original_count) if index not in keep)
    keep.update(_sample_indexes(noncritical, remaining_quota))
    selected = [points[index] for index in sorted(keep)]
    return ReplaySimplificationResult(
        points=selected,
        original_point_count=original_count,
        returned_point_count=len(selected),
        max_points=max_points,
        simplified=len(selected) < original_count,
        task_aware=task_aware,
    )
