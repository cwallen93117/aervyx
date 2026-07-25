from datetime import UTC, date, datetime, timedelta

import pytest

from app.models import Event, ScorePenalty, Task, TaskPoint, TrackPoint
from app.services.airscore import task as airscore_task_module
from app.services.airscore.gap import select_coeff
from app.services.handicap import validate_handicap_config
from app.services.scoring import (
    _as_utc_aware,
    _build_airscore_pilot_result,
    _build_formula,
    _compute_leading_coeff,
    _compute_optimized_task_distance,
    _minimum_distance_evaluation,
    _prepare_waypoints_for_distance,
    _resolve_task_time_utc,
    _resolve_timezone_name,
    _score_evaluations,
    evaluate_task,
)


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


def _track_point_at(sequence: int, recorded_at: datetime, lat: float, lon: float) -> TrackPoint:
    point = TrackPoint(upload_id=1, sequence=sequence, recorded_at=recorded_at, latitude=lat, longitude=lon)
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
    result = evaluate_task(_task(), task_points, track_points)
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
    result = evaluate_task(_task(), task_points, track_points)
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
            {"upload": upload_a, "evaluation": evaluate_task(_task(nominal_time_hours=0.05), task_points, winning_track)},
            {"upload": upload_b, "evaluation": evaluate_task(_task(nominal_time_hours=0.05), task_points, trailing_track)},
        ],
    )

    assert scored[0]["pilot_id"] == 1
    assert scored[0]["score_points"] > scored[1]["score_points"]
    gap = scored[0]["details_json"]["gap"]
    assert gap["available_points"]["distance"] > 0
    assert gap["awarded_points"]["speed"] >= 0
    assert gap["validity"]["overall"] > 0


def test_start_time_uses_exit_of_start_cylinder_after_open_time() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.start_open_time = "13:30:00"
    task.start_close_time = "20:00:00"
    task.task_start_time = "13:30:00"
    task.task_finish_time = "20:00:00"
    task_points = [
        _task_point(1, 1, "start", 39.09639, -75.89061, 5000),
        _task_point(2, 2, "goal", 38.68586, -75.07051, 400),
    ]
    track_points = [
        _track_point_at(1, datetime(2025, 6, 2, 18, 22, 23, tzinfo=UTC), 39.09703, -75.89203),
        _track_point_at(2, datetime(2025, 6, 2, 18, 30, 0, tzinfo=UTC), 39.096, -75.94),
        _track_point_at(3, datetime(2025, 6, 2, 18, 33, 53, tzinfo=UTC), 39.05, -75.96),
        _track_point_at(4, datetime(2025, 6, 2, 20, 46, 11, tzinfo=UTC), 38.68586, -75.07051),
    ]
    result = evaluate_task(task, task_points, track_points, event_timezone="Eastern")
    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[1].recorded_at.isoformat()
    assert result["details"]["start_timing"]["start_scoring_mode"] == "elapsed_time"
    assert result["details"]["start_timing"]["start_gate_index"] is None
    assert result["started_at"] == track_points[1].recorded_at
    assert result["goal_at"] == track_points[3].recorded_at


def test_elapsed_scoring_ignores_stale_start_open_time() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.task_start_time = "13:30:00"
    task.start_open_time = "14:30:00"
    task.start_close_time = "20:00:00"
    task.task_finish_time = "20:00:00"
    task_points = [
        _task_point(1, 1, "start", 39.09639, -75.89061, 5000),
        _task_point(2, 2, "goal", 38.68586, -75.07051, 400),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 5, 4, 13, 25, 0, tzinfo=UTC), 39.09703, -75.89203),
        _track_point_at(2, datetime(2026, 5, 4, 13, 35, 0, tzinfo=UTC), 39.096, -75.94),
        _track_point_at(3, datetime(2026, 5, 4, 13, 50, 0, tzinfo=UTC), 38.68586, -75.07051),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[1].recorded_at.isoformat()
    assert result["details"]["start_timing"]["scored_start_at"] == track_points[1].recorded_at.isoformat()
    assert result["started_at"] == track_points[1].recorded_at
    assert result["goal_at"] == track_points[2].recorded_at


def test_elapsed_enter_start_uses_outside_fix_before_entry_as_start_time() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.start_open_time = "12:00:00"
    task.start_close_time = "18:00:00"
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    task_points[0].direction = "enter"
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 5, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(2, datetime(2026, 3, 17, 12, 6, tzinfo=UTC), 0.0, 0.004),
        _track_point_at(3, datetime(2026, 3, 17, 13, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["details"]["start_timing"]["actual_start_exit_after_at"] == track_points[1].recorded_at.isoformat()
    assert result["started_at"] == track_points[0].recorded_at


def test_elapsed_start_before_open_scores_open_time_with_jump_penalty() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.start_open_time = "12:00:00"
    task.start_close_time = "18:00:00"
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    event = type("EventStub", (), {"jump_the_gun_factor": 2.0, "jump_the_gun_max_seconds": 300})()
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 11, 59, 30, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 11, 59, 40, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 13, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC", event=event)

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["started_at"] == datetime(2026, 3, 17, 12, 0, tzinfo=UTC)
    assert result["details"]["start_timing"]["jump_the_gun_seconds"] == 30
    assert result["jump_the_gun_penalty_points"] == 60


def test_elapsed_start_after_close_is_detected_and_scored_at_start_close() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.start_open_time = "12:00:00"
    task.start_close_time = "12:30:00"
    task.task_finish_time = "18:00:00"
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 13, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 13, 1, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 14, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["details"]["start_timing"]["scored_start_at"] == datetime(2026, 3, 17, 12, 30, tzinfo=UTC).isoformat()
    assert result["started_at"] == datetime(2026, 3, 17, 12, 30, tzinfo=UTC)
    assert result["elapsed_seconds"] == 90 * 60


def test_missed_start_detection_does_not_leak_epoch_into_end_ss() -> None:
    """If the start cylinder is not detected but ESS/goal are, the pilot's
    AirScore result dict must keep both startSS and endSS zero. Leaving endSS
    as a Unix epoch timestamp (while startSS=0) poisons build_task_totals,
    which computes time as (endSS - startSS) and yields ~1.7B seconds as the
    fastest time — breaking time validity and all downstream scoring."""
    evaluation = {
        "status": "goal",
        "distance_flown_km": 10.0,
        "started_at": None,  # start cylinder miss
        "ess_at": datetime(2024, 6, 29, 18, 18, 16, tzinfo=UTC),
        "goal_at": datetime(2024, 6, 29, 18, 28, 24, tzinfo=UTC),
        "elapsed_seconds": None,
        "leading_coeff": 0,
        "leading_coeff2": 0,
    }
    result = _build_airscore_pilot_result(pilot_id=1, evaluation=evaluation)
    assert result["startSS"] == 0
    assert result["endSS"] == 0
    assert result["time"] == 0


def test_exit_start_uses_later_recrossing_inside_fix() -> None:
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 12, 2, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(4, datetime(2026, 3, 17, 12, 3, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(5, datetime(2026, 3, 17, 12, 10, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(_task(), task_points, track_points)

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[2].recorded_at.isoformat()
    assert result["started_at"] == track_points[2].recorded_at


def test_hc_2025_elapsed_restart_chooses_later_start_crossing() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task.start_open_time = "14:00:00"
    task.start_close_time = "15:00:00"
    task.task_finish_time = "19:00:00"
    task_points = [
        _task_point(1, 1, "start", 39.09639, -75.89061, 5000),
        _task_point(2, 2, "goal", 38.68586, -75.07051, 400),
    ]
    track_points = [
        _track_point_at(1, datetime(2025, 6, 2, 18, 6, tzinfo=UTC), 39.09639, -75.89061),
        _track_point_at(2, datetime(2025, 6, 2, 18, 7, tzinfo=UTC), 39.09639, -75.95000),
        _track_point_at(3, datetime(2025, 6, 2, 18, 30, tzinfo=UTC), 39.09639, -75.89061),
        _track_point_at(4, datetime(2025, 6, 2, 18, 33, tzinfo=UTC), 39.09639, -75.95000),
        _track_point_at(5, datetime(2025, 6, 2, 20, 46, tzinfo=UTC), 38.68586, -75.07051),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="America/New_York")

    assert result["details"]["engine"] == "airscore.verify"
    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[2].recorded_at.isoformat()
    assert result["started_at"] == track_points[2].recorded_at


def test_elapsed_restart_stops_after_next_waypoint_is_made() -> None:
    task = _task()
    task.task_type = "elapsed_time"
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "turnpoint", 0.0, 0.02, 1000),
        _task_point(3, 3, "turnpoint", 0.0, -0.02, 1000),
        _task_point(4, 4, "goal", 0.0, -0.04, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 7, 19, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 7, 19, 12, 1, tzinfo=UTC), 0.0, 0.01),
        _track_point_at(3, datetime(2026, 7, 19, 12, 2, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(4, datetime(2026, 7, 19, 12, 3, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(5, datetime(2026, 7, 19, 12, 4, tzinfo=UTC), 0.0, -0.01),
        _track_point_at(6, datetime(2026, 7, 19, 12, 5, tzinfo=UTC), 0.0, -0.02),
        _track_point_at(7, datetime(2026, 7, 19, 12, 6, tzinfo=UTC), 0.0, -0.04),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["status"] == "goal"
    assert result["started_at"] == track_points[0].recorded_at
    assert all(hit["hit"] for hit in result["details"]["hits"])


def test_enter_points_use_first_inside_fix_after_entry() -> None:
    task_points = [
        _task_point(1, 1, "start", 0.0, -0.04, 1000),
        _task_point(2, 2, "turnpoint", 0.0, 0.0, 1000),
        _task_point(3, 3, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, -0.04),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.0, -0.02),
        _track_point_at(3, datetime(2026, 3, 17, 12, 2, tzinfo=UTC), 0.0, -0.02),
        _track_point_at(4, datetime(2026, 3, 17, 12, 3, tzinfo=UTC), 0.0, -0.005),
        _track_point_at(5, datetime(2026, 3, 17, 12, 4, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(6, datetime(2026, 3, 17, 12, 8, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(_task(), task_points, track_points)
    turnpoint_hit = result["details"]["hits"][1]

    assert turnpoint_hit["hit_at"] == track_points[3].recorded_at.isoformat()


def test_enter_start_uses_outside_fix_before_entry_for_scoring_point() -> None:
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    task_points[0].direction = "enter"
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.0, 0.004),
        _track_point_at(3, datetime(2026, 3, 17, 12, 10, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(_task(), task_points, track_points)
    start_hit = result["details"]["hits"][0]

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["details"]["start_timing"]["actual_start_exit_after_at"] == track_points[1].recorded_at.isoformat()
    assert start_hit["track_point"]["sequence"] == track_points[0].sequence


def test_gated_race_start_uses_latest_prior_gate() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.start_gate_count = 5
    task.start_gate_interval_seconds = 20 * 60
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 14, 38, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 14, 39, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 15, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["started_at"] == datetime(2026, 3, 17, 14, 20, tzinfo=UTC)
    assert result["elapsed_seconds"] == 40 * 60


def test_exit_start_uses_gate_opening_inside_exit_interval() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 14, 17, 30, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 14, 20, 30, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 16, 34, 17, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[0].recorded_at.isoformat()
    assert result["details"]["start_timing"]["actual_start_exit_after_at"] == track_points[1].recorded_at.isoformat()
    assert result["started_at"] == datetime(2026, 3, 17, 14, 20, tzinfo=UTC)
    assert result["elapsed_seconds"] == (2 * 3600) + (14 * 60) + 17


def test_before_first_gate_start_scores_first_gate_with_jump_penalty() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.start_gate_count = 5
    task.start_gate_interval_seconds = 15 * 60
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    event = type("EventStub", (), {"jump_the_gun_factor": 2.0, "jump_the_gun_max_seconds": 300})()
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 13, 59, 30, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 13, 59, 40, tzinfo=UTC), 0.02, 0.0),
        _track_point_at(3, datetime(2026, 3, 17, 15, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC", event=event)
    pilot_result = _build_airscore_pilot_result(result, pilot_id=1)

    assert result["started_at"] == datetime(2026, 3, 17, 14, 0, tzinfo=UTC)
    assert result["details"]["start_timing"]["jump_the_gun_seconds"] == 30
    assert result["jump_the_gun_penalty_points"] == 60
    assert pilot_result["penalty"] == 60


def test_exit_start_uses_last_inside_fix_before_actual_exit() -> None:
    task = _task()
    task.start_open_time = "12:00:00"
    task.task_finish_time = "18:00:00"
    event = type("EventStub", (), {"turnpoint_radius_tolerance": 0.001, "turnpoint_radius_minimum_absolute_tolerance_m": 5})()
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.0, 0.004),
        _track_point_at(3, datetime(2026, 3, 17, 12, 2, tzinfo=UTC), 0.0, 0.0092),
        _track_point_at(4, datetime(2026, 3, 17, 12, 10, tzinfo=UTC), 0.04, 0.0),
    ]
    track_points[1].pressure_altitude_m = 321

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC", event=event)
    start_hit = result["details"]["hits"][0]

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[1].recorded_at.isoformat()
    assert start_hit["hit_at"] == track_points[1].recorded_at.isoformat()
    assert result["details"]["start_timing"]["actual_start_exit_after_at"] == track_points[2].recorded_at.isoformat()
    assert start_hit["track_point"]["sequence"] == track_points[1].sequence
    assert start_hit["track_point"]["altitude_m"] == 321


def test_exit_start_rearms_from_airscore_margin_for_later_gate() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "12:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task.task_finish_time = "18:00:00"
    event = type("EventStub", (), {"turnpoint_radius_tolerance": 0.001, "turnpoint_radius_minimum_absolute_tolerance_m": 5})()
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 13, 55, tzinfo=UTC), 0.0, 0.004),
        _track_point_at(2, datetime(2026, 3, 17, 12, 13, 56, tzinfo=UTC), 0.0, 0.0092),
        _track_point_at(3, datetime(2026, 3, 17, 12, 41, 0, tzinfo=UTC), 0.0, 0.004),
        _track_point_at(4, datetime(2026, 3, 17, 12, 41, 1, tzinfo=UTC), 0.0, 0.0092),
        _track_point_at(5, datetime(2026, 3, 17, 14, 0, tzinfo=UTC), 0.04, 0.0),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC", event=event)

    assert result["details"]["start_timing"]["actual_start_crossing_at"] == track_points[2].recorded_at.isoformat()
    assert result["started_at"] == datetime(2026, 3, 17, 12, 40, tzinfo=UTC)


def test_leading_coeff_accumulates_from_verified_start_crossing() -> None:
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.08, 0.0, 1000),
    ]
    _, waypoints = _compute_optimized_task_distance(task_points)
    distance_waypoints, _ = _prepare_waypoints_for_distance(waypoints, {"errormargin": 0.05})
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 12, 5, tzinfo=UTC), 0.0, 0.0085),
        _track_point_at(3, datetime(2026, 3, 17, 12, 6, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(4, datetime(2026, 3, 17, 12, 20, tzinfo=UTC), 0.08, 0.0),
    ]
    full_distance_m = distance_waypoints[0]["_totdist"]
    target_indices = [0, 0, 1, 1]

    without_reset, _ = _compute_leading_coeff(
        distance_waypoints,
        track_points,
        started_at=track_points[1].recorded_at,
        ess_at=track_points[3].recorded_at,
        distance_flown_m=full_distance_m,
        task_class="HG",
        task_sstart=track_points[0].recorded_at.timestamp(),
        task_sfinish=(track_points[0].recorded_at + timedelta(hours=6)).timestamp(),
        target_waypoint_indices=target_indices,
    )
    with_reset, _ = _compute_leading_coeff(
        distance_waypoints,
        track_points,
        started_at=track_points[1].recorded_at,
        ess_at=track_points[3].recorded_at,
        distance_flown_m=full_distance_m,
        task_class="HG",
        task_sstart=track_points[0].recorded_at.timestamp(),
        task_sfinish=(track_points[0].recorded_at + timedelta(hours=6)).timestamp(),
        target_waypoint_indices=target_indices,
        actual_start_index=1,
    )

    assert without_reset == 0
    assert with_reset > 0


def test_airscore_distance_precompute_resets_dynamic_waypoint_state() -> None:
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.08, 0.0, 1000),
    ]
    _, waypoints = _compute_optimized_task_distance(task_points)

    airscore_task_module._last_wpt_update = datetime(2026, 3, 17, 12, 0, tzinfo=UTC).timestamp()
    _prepare_waypoints_for_distance(waypoints, {"errormargin": 0.05})

    assert airscore_task_module._last_wpt_update == 0.0


def test_goal_ss_penalty_preserves_explicit_zero() -> None:
    event = type("EventStub", (), {"goal_ss_penalty": 0.0})()

    formula = _build_formula(_task(), event)

    assert formula["sspenalty"] == 0.0


def test_formula_uses_event_parameters_instead_of_task_defaults() -> None:
    task = _task()
    task.minimum_distance_km = 3
    task.nominal_distance_km = 123
    task.nominal_time_hours = 4
    task.nominal_launch = 0.99
    task.penalties_json = {"lineardist": 0.1}
    event = Event(
        name="HC 2025",
        location="Maryland",
        starts_on=date(2025, 5, 30),
        ends_on=date(2025, 6, 7),
        minimum_distance_km=5,
        nominal_distance_km=55,
        nominal_time_hours=1.5,
        nominal_launch=0.4,
        penalties_json={"lineardist": 0.5},
    )

    formula = _build_formula(task, event)

    assert formula["mindist_km"] == 5
    assert formula["nomdist_km"] == 55
    assert formula["nomtime_seconds"] == 1.5 * 3600
    assert formula["nomlaunch"] == 0.4
    assert formula["lineardist"] == 0.5


def test_formula_missing_event_values_use_defaults_not_task_values() -> None:
    task = _task()
    task.minimum_distance_km = 9
    task.nominal_distance_km = 99
    task.nominal_time_hours = 9
    task.nominal_launch = 0.9
    event = Event(
        name="Legacy Event",
        location="Somewhere",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 2),
    )

    formula = _build_formula(task, event)

    assert formula["mindist_km"] == 5
    assert formula["nomdist_km"] == 60
    assert formula["nomtime_seconds"] == 1.5 * 3600
    assert formula["nomlaunch"] == 0.95


def test_minimum_distance_override_uses_event_minimum_distance() -> None:
    task = _task()
    task.minimum_distance_km = 3
    event = Event(
        name="Minimum Distance Event",
        location="Somewhere",
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 1, 2),
        minimum_distance_km=7,
    )

    evaluation = _minimum_distance_evaluation(task, event)

    assert evaluation["distance_flown_km"] == 7


def _fl_2026_task_points() -> list[TaskPoint]:
    return [
        _task_point(1, 1, "launch", 28.53303, -81.84666, 400),
        _task_point(2, 2, "start", 28.53303, -81.84666, 5000),
        _task_point(3, 3, "turnpoint", 28.95917, -82.13416, 1000),
        _task_point(4, 4, "turnpoint", 29.06043, -82.37565, 3000),
        _task_point(5, 5, "turnpoint", 29.28913, -82.32232, 1000),
        _task_point(6, 6, "goal", 29.06043, -82.37565, 3000),
    ]


def test_fl_2026_launch_radius_does_not_reduce_start_distance() -> None:
    task_distance_km, waypoints = _compute_optimized_task_distance(_fl_2026_task_points())

    assert task_distance_km == pytest.approx(123.84, abs=0.03)
    assert waypoints[0]["_startssdist"] / 1000 == pytest.approx(5.0, abs=0.01)
    assert waypoints[0]["_ssdist"] / 1000 == pytest.approx(118.84, abs=0.03)


def test_missed_turnpoint_blocks_later_goal_credit() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    task.start_gate_count = 5
    task.start_gate_interval_seconds = 15 * 60
    task_points = _fl_2026_task_points()
    track_points = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 0, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, tzinfo=UTC), 28.57, -81.91),
        # Near SAVANA but outside the 1 km cylinder.
        _track_point_at(3, datetime(2026, 4, 23, 19, 0, tzinfo=UTC), 28.93917, -82.13416),
        # Later cylinders are reached, but they must not count after the miss.
        _track_point_at(4, datetime(2026, 4, 23, 19, 30, tzinfo=UTC), 29.06043, -82.37565),
        _track_point_at(5, datetime(2026, 4, 23, 20, 15, tzinfo=UTC), 29.28913, -82.32232),
        _track_point_at(6, datetime(2026, 4, 23, 21, 0, tzinfo=UTC), 29.06043, -82.37565),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="America/New_York")
    later_goal = result["details"]["hits"][-1]

    assert result["status"] == "partial"
    assert result["goal_at"] is None
    assert result["details"]["missed_point"]["task_point_id"] == 3
    assert later_goal["hit"] is False
    assert later_goal["ignored_hit"] is True
    assert result["distance_flown_km"] > 40
    assert result["distance_flown_km"] < 55


def test_fl_2026_timezone_inference_scores_first_gate_as_eastern_time() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task_points = _fl_2026_task_points()
    track_points = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, 20, tzinfo=UTC), 28.57, -81.91),
        _track_point_at(3, datetime(2026, 4, 23, 20, 34, 17, tzinfo=UTC), 29.06043, -82.37565),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["details"]["scoring_timezone"] == "America/New_York"
    assert result["started_at"] == datetime(2026, 4, 23, 18, 20, tzinfo=UTC)
    assert result["details"]["start_timing"]["start_gate_index"] == 2


def test_est_alias_scores_florida_gates_as_eastern_time() -> None:
    task = _task()
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task_points = _fl_2026_task_points()
    track_points = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, 20, tzinfo=UTC), 28.57, -81.91),
        _track_point_at(3, datetime(2026, 4, 23, 20, 34, 17, tzinfo=UTC), 29.06043, -82.37565),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="EST")

    assert _resolve_timezone_name("EST") == "America/New_York"
    assert result["details"]["scoring_timezone"] == "America/New_York"
    assert result["started_at"] == datetime(2026, 4, 23, 18, 20, tzinfo=UTC)
    assert result["details"]["start_timing"]["start_gate_index"] == 2


def test_task_clock_resolution_treats_naive_track_timestamps_as_utc() -> None:
    task = _task()
    task.start_open_time = "14:00:00"
    naive_trackpoints = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31), 28.53303, -81.84666),
    ]

    resolved = _resolve_task_time_utc(task.start_open_time, naive_trackpoints, "America/New_York")

    assert resolved == datetime(2026, 4, 23, 18, 0, tzinfo=UTC)
    assert _as_utc_aware(datetime(2026, 4, 23, 18, 20)) == datetime(2026, 4, 23, 18, 20, tzinfo=UTC)


def test_flown_track_without_start_receives_minimum_distance_for_display() -> None:
    task = _task()
    task.minimum_distance_km = 5
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "goal", 0.04, 0.0, 1000),
    ]
    track_points = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.04, 0.04),
        _track_point_at(2, datetime(2026, 3, 17, 12, 5, tzinfo=UTC), 0.05, 0.05),
    ]

    result = evaluate_task(task, task_points, track_points, event_timezone="UTC")

    assert result["status"] == "partial"
    assert result["distance_flown_km"] == 5.0


def test_minimum_distance_override_counts_as_flown_for_gap_distribution() -> None:
    task = _task()
    evaluation = _minimum_distance_evaluation(task)

    result = _build_airscore_pilot_result(evaluation, pilot_id=127)

    assert result["result"] == "lo"
    assert result["goal"] == 0
    assert result["distance"] == pytest.approx(5000)


def test_gap2025_uses_distance_squared_leading_coeff2() -> None:
    task = _task(nominal_time_hours=1.5)
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    _, waypoints = _compute_optimized_task_distance(_fl_2026_task_points())
    start = datetime(2026, 4, 23, 18, 20, tzinfo=UTC)
    finish = datetime(2026, 4, 23, 20, 34, tzinfo=UTC)
    event = type(
        "EventStub",
        (),
        {
            "timezone": "America/New_York",
            "scoring_formula": "GAP2025",
            "penalties_json": {"is_pg_comp": 0},
            "nominal_distance_km": 50,
            "nominal_time_hours": 1.5,
            "nominal_launch": 0.96,
            "minimum_distance_km": 5,
            "nominal_goal_percent": 0.3,
            "goal_ss_penalty": 0.0,
            "time_points_if_not_in_goal": 0.8,
            "use_distance_points": True,
            "use_time_points": True,
            "use_leading_points": True,
            "use_arrival_position_points": True,
            "use_arrival_time_points": False,
            "use_departure_points": False,
            "use_difficulty_for_distance_points": True,
            "use_flat_decline_of_timepoints": True,
            "use_distance_squared_for_lc": True,
            "leading_weight_factor": 1.0,
        },
    )()

    def evaluation(pilot_id: int, coeff: float, coeff2: float) -> dict:
        return {
            "pilot_id": pilot_id,
            "upload": type("UploadStub", (), {"id": pilot_id, "pilot_id": pilot_id})(),
            "evaluation": {
                "status": "goal",
                "distance_flown_km": 123.843,
                "started_at": start,
                "ess_at": finish,
                "goal_at": finish,
                "elapsed_seconds": int((finish - start).total_seconds()),
                "leading_coeff": coeff,
                "leading_coeff2": coeff2,
                "jump_the_gun_penalty_points": 0,
                "details": {"hits": [], "total_distance_km": 123.843, "scoring_timezone": "America/New_York"},
            },
        }

    scored = _score_evaluations(
        task,
        22,
        [
            evaluation(1, coeff=100.0, coeff2=1.0),
            evaluation(2, coeff=1.0, coeff2=100.0),
        ],
        event,
        airscore_waypoints=waypoints,
    )
    leading_by_pilot = {
        row["pilot_id"]: row["details_json"]["gap"]["awarded_points"]["leading"]
        for row in scored
    }

    assert leading_by_pilot[1] > leading_by_pilot[2]
    assert scored[0]["details_json"]["gap"]["leading_coefficients"]["selected_field"] == "tarLeadingCoeff2"


def test_gap2025_uses_flat_leading_coeff_when_distance_squared_lc_is_off() -> None:
    assert select_coeff({"class": "gap", "version": 2025, "use_distance_squared_for_lc": False}) == "tarLeadingCoeff"

    task = _task(nominal_time_hours=1.5)
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    _, waypoints = _compute_optimized_task_distance(_fl_2026_task_points())
    start = datetime(2026, 4, 23, 18, 20, tzinfo=UTC)
    finish = datetime(2026, 4, 23, 20, 34, tzinfo=UTC)
    event = type(
        "EventStub",
        (),
        {
            "timezone": "EST",
            "scoring_formula": "GAP2025",
            "penalties_json": {"is_pg_comp": 0},
            "nominal_distance_km": 50,
            "nominal_time_hours": 1.5,
            "nominal_launch": 0.96,
            "minimum_distance_km": 5,
            "nominal_goal_percent": 0.3,
            "goal_ss_penalty": 0.0,
            "time_points_if_not_in_goal": 0.8,
            "use_distance_points": True,
            "use_time_points": True,
            "use_leading_points": True,
            "use_arrival_position_points": True,
            "use_arrival_time_points": False,
            "use_departure_points": False,
            "use_difficulty_for_distance_points": True,
            "use_flat_decline_of_timepoints": True,
            "use_distance_squared_for_lc": False,
            "leading_weight_factor": 1.0,
        },
    )()

    def evaluation(pilot_id: int, coeff: float, coeff2: float) -> dict:
        return {
            "pilot_id": pilot_id,
            "upload": type("UploadStub", (), {"id": pilot_id, "pilot_id": pilot_id})(),
            "evaluation": {
                "status": "goal",
                "distance_flown_km": 123.843,
                "started_at": start,
                "ess_at": finish,
                "goal_at": finish,
                "elapsed_seconds": int((finish - start).total_seconds()),
                "leading_coeff": coeff,
                "leading_coeff2": coeff2,
                "jump_the_gun_penalty_points": 0,
                "details": {"hits": [], "total_distance_km": 123.843, "scoring_timezone": "America/New_York"},
            },
        }

    scored = _score_evaluations(
        task,
        22,
        [
            evaluation(1, coeff=1.0, coeff2=100.0),
            evaluation(2, coeff=100.0, coeff2=1.0),
        ],
        event,
        airscore_waypoints=waypoints,
    )
    leading_by_pilot = {
        row["pilot_id"]: row["details_json"]["gap"]["awarded_points"]["leading"]
        for row in scored
    }

    assert leading_by_pilot[1] > leading_by_pilot[2]
    assert scored[0]["details_json"]["gap"]["leading_coefficients"]["selected_field"] == "tarLeadingCoeff"


def test_landed_out_pilot_can_receive_leading_points_after_waypoint_progress() -> None:
    task = _task(nominal_time_hours=1.5)
    task.task_type = "race_to_goal_with_gates"
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task_points = _fl_2026_task_points()
    distance_km, waypoints = _compute_optimized_task_distance(task_points)
    event = type(
        "EventStub",
        (),
        {
            "timezone": "America/New_York",
            "scoring_formula": "GAP2025",
            "penalties_json": {"is_pg_comp": 0},
            "nominal_distance_km": 50,
            "nominal_time_hours": 1.5,
            "nominal_launch": 0.96,
            "minimum_distance_km": 5,
            "nominal_goal_percent": 0.3,
            "goal_ss_penalty": 0.0,
            "time_points_if_not_in_goal": 0.8,
            "use_distance_points": True,
            "use_time_points": True,
            "use_leading_points": True,
            "use_arrival_position_points": True,
            "use_arrival_time_points": False,
            "use_departure_points": False,
            "use_difficulty_for_distance_points": True,
            "use_flat_decline_of_timepoints": True,
            "use_distance_squared_for_lc": True,
            "leading_weight_factor": 1.0,
        },
    )()
    goal_track = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, 20, tzinfo=UTC), 28.57, -81.91),
        _track_point_at(3, datetime(2026, 4, 23, 19, 10, tzinfo=UTC), 28.95917, -82.13416),
        _track_point_at(4, datetime(2026, 4, 23, 19, 50, tzinfo=UTC), 29.06043, -82.37565),
        _track_point_at(5, datetime(2026, 4, 23, 20, 20, tzinfo=UTC), 29.28913, -82.32232),
        _track_point_at(6, datetime(2026, 4, 23, 20, 34, 17, tzinfo=UTC), 29.06043, -82.37565),
    ]
    landed_out_track = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, 20, tzinfo=UTC), 28.57, -81.91),
        _track_point_at(3, datetime(2026, 4, 23, 18, 50, tzinfo=UTC), 28.95917, -82.13416),
        _track_point_at(4, datetime(2026, 4, 23, 19, 20, tzinfo=UTC), 29.06043, -82.37565),
        _track_point_at(5, datetime(2026, 4, 23, 19, 50, tzinfo=UTC), 29.28913, -82.32232),
        _track_point_at(6, datetime(2026, 4, 23, 20, 0, tzinfo=UTC), 29.2, -82.35),
    ]

    scored = _score_evaluations(
        task,
        22,
        [
            {
                "pilot_id": 1,
                "upload": type("UploadStub", (), {"id": 1, "pilot_id": 1})(),
                "evaluation": evaluate_task(task, task_points, goal_track, event_timezone="America/New_York", optimized_distance_km=distance_km, airscore_waypoints=waypoints, task_class="HG", event=event),
            },
            {
                "pilot_id": 2,
                "upload": type("UploadStub", (), {"id": 2, "pilot_id": 2})(),
                "evaluation": evaluate_task(task, task_points, landed_out_track, event_timezone="America/New_York", optimized_distance_km=distance_km, airscore_waypoints=waypoints, task_class="HG", event=event),
            },
        ],
        event,
        airscore_waypoints=waypoints,
    )
    landed_out = next(row for row in scored if row["pilot_id"] == 2)
    awarded = landed_out["details_json"]["gap"]["awarded_points"]

    assert landed_out["status"] == "partial"
    assert awarded["speed"] == 0
    assert awarded["arrival"] == 0
    assert awarded["leading"] > 0


def test_non_goal_pilot_loses_speed_and_arrival_points() -> None:
    task = _task(nominal_time_hours=0.05)
    task.start_open_time = "12:00:00"
    task.task_finish_time = "18:00:00"
    task_points = [
        _task_point(1, 1, "start", 0.0, 0.0, 1000),
        _task_point(2, 2, "turnpoint", 0.0, 0.04, 1000),
        _task_point(3, 3, "goal", 0.0, 0.08, 1000),
    ]
    goal_track = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(3, datetime(2026, 3, 17, 12, 8, tzinfo=UTC), 0.0, 0.04),
        _track_point_at(4, datetime(2026, 3, 17, 12, 16, tzinfo=UTC), 0.0, 0.08),
    ]
    partial_track = [
        _track_point_at(1, datetime(2026, 3, 17, 12, 0, tzinfo=UTC), 0.0, 0.0),
        _track_point_at(2, datetime(2026, 3, 17, 12, 1, tzinfo=UTC), 0.0, 0.02),
        _track_point_at(3, datetime(2026, 3, 17, 12, 8, tzinfo=UTC), 0.0, 0.04),
        _track_point_at(4, datetime(2026, 3, 17, 12, 20, tzinfo=UTC), 0.0, 0.06),
    ]
    upload_goal = type("UploadStub", (), {"id": 10, "pilot_id": 1})()
    upload_partial = type("UploadStub", (), {"id": 11, "pilot_id": 2})()

    scored = _score_evaluations(
        task,
        2,
        [
            {"upload": upload_goal, "evaluation": evaluate_task(task, task_points, goal_track, event_timezone="UTC")},
            {"upload": upload_partial, "evaluation": evaluate_task(task, task_points, partial_track, event_timezone="UTC")},
        ],
    )
    partial = next(result for result in scored if result["pilot_id"] == 2)
    awarded = partial["details_json"]["gap"]["awarded_points"]

    assert partial["status"] == "partial"
    assert awarded["distance"] > 0
    assert awarded["speed"] == 0
    assert awarded["arrival"] == 0


def test_hg_gap2025_leading_and_arrival_weights_are_available() -> None:
    task = _task(nominal_time_hours=1.5)
    task.start_open_time = "14:00:00"
    task.task_finish_time = "19:00:00"
    task.start_gate_count = 4
    task.start_gate_interval_seconds = 20 * 60
    task_points = _fl_2026_task_points()
    goal_track = [
        _track_point_at(1, datetime(2026, 4, 23, 18, 17, 31, tzinfo=UTC), 28.53303, -81.84666),
        _track_point_at(2, datetime(2026, 4, 23, 18, 20, 20, tzinfo=UTC), 28.57, -81.91),
        _track_point_at(3, datetime(2026, 4, 23, 19, 10, tzinfo=UTC), 28.95917, -82.13416),
        _track_point_at(4, datetime(2026, 4, 23, 19, 50, tzinfo=UTC), 29.06043, -82.37565),
        _track_point_at(5, datetime(2026, 4, 23, 20, 20, tzinfo=UTC), 29.28913, -82.32232),
        _track_point_at(6, datetime(2026, 4, 23, 20, 34, 17, tzinfo=UTC), 29.06043, -82.37565),
    ]
    event = type(
        "EventStub",
        (),
        {
            "timezone": "America/New_York",
            "scoring_formula": "GAP2025",
            "penalties_json": {"is_pg_comp": 0},
            "nominal_distance_km": 50,
            "nominal_time_hours": 1.5,
            "nominal_launch": 0.96,
            "minimum_distance_km": 5,
            "nominal_goal_percent": 0.3,
            "goal_ss_penalty": 0.0,
            "time_points_if_not_in_goal": 0.8,
            "use_distance_points": True,
            "use_time_points": True,
            "use_leading_points": True,
            "use_arrival_position_points": True,
            "use_arrival_time_points": False,
            "use_departure_points": False,
            "use_difficulty_for_distance_points": True,
            "use_flat_decline_of_timepoints": True,
            "leading_weight_factor": 1.0,
        },
    )()
    upload = type("UploadStub", (), {"id": 10, "pilot_id": 1})()
    distance_km, waypoints = _compute_optimized_task_distance(task_points)
    scored = _score_evaluations(
        task,
        22,
        [{"upload": upload, "evaluation": evaluate_task(task, task_points, goal_track, event_timezone="America/New_York", optimized_distance_km=distance_km, airscore_waypoints=waypoints, task_class="HG", event=event)}],
        event,
        airscore_waypoints=waypoints,
    )
    available = scored[0]["details_json"]["gap"]["available_points"]

    assert available["leading"] > 0
    assert available["arrival"] > 0
    assert available["speed"] > 0


def test_launch_validity_saturates_at_one_for_well_launched_day() -> None:
    task = _task(nominal_time_hours=0.05)
    winning_track = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.700, -118.100),
        _track_point(4, 36.750, -118.150),
        _track_point(5, 36.800, -118.200),
    ]
    upload = type("UploadStub", (), {"id": 10, "pilot_id": 1})()

    event = type(
        "EventStub",
        (),
        {
            "nominal_goal_percent": 0.2,
            "use_distance_points": True,
            "use_time_points": True,
            "use_departure_points": False,
            "use_arrival_position_points": False,
            "use_arrival_time_points": False,
            "use_difficulty_for_distance_points": True,
            "goal_ss_penalty": 0.0,
        },
    )()

    scored = _score_evaluations(
        task,
        1,
        [{"upload": upload, "evaluation": evaluate_task(task, [_task_point(1, 1, "launch", 36.600, -118.000, 500), _task_point(2, 2, "start", 36.650, -118.050, 1000), _task_point(3, 3, "turnpoint", 36.700, -118.100, 600), _task_point(4, 4, "ESS", 36.750, -118.150, 1000), _task_point(5, 5, "goal", 36.800, -118.200, 500)], winning_track)}],
        event,
    )
    gap = scored[0]["details_json"]["gap"]
    assert gap["validity"]["launch"] == 1.0
    assert gap["available_points"]["distance"] > 0
    assert gap["available_points"]["speed"] > 0


def test_mixed_class_handicap_runs_after_airscore_before_manual_penalties_and_sets_rank() -> None:
    task = _task(nominal_time_hours=0.05)
    task_points = [
        _task_point(1, 1, "launch", 36.600, -118.000, 500),
        _task_point(2, 2, "start", 36.650, -118.050, 1000),
        _task_point(3, 3, "turnpoint", 36.700, -118.100, 600),
        _task_point(4, 4, "ESS", 36.750, -118.150, 1000),
        _task_point(5, 5, "goal", 36.800, -118.200, 500),
    ]
    track = [
        _track_point(1, 36.600, -118.000),
        _track_point(2, 36.650, -118.050),
        _track_point(3, 36.700, -118.100),
        _track_point(4, 36.750, -118.150),
        _track_point(5, 36.800, -118.200),
    ]
    event = type(
        "EventStub",
        (),
        {
            "nominal_goal_percent": 0.2,
            "use_distance_points": True,
            "use_time_points": True,
            "use_departure_points": False,
            "use_arrival_position_points": False,
            "use_arrival_time_points": False,
            "use_difficulty_for_distance_points": True,
            "goal_ss_penalty": 0.0,
            "penalties_json": {
                "handicap": {
                    "enabled": True,
                    "multipliers": {
                        "modern_topless": 1,
                        "high_performance_kingpost": 1.05,
                        "intermediate_kingpost": 1.1,
                        "single_surface": 1.2,
                    },
                }
            },
        },
    )()
    scored = _score_evaluations(
        task,
        2,
        [
            {"upload": type("UploadStub", (), {"id": 10, "pilot_id": 1})(), "evaluation": evaluate_task(task, task_points, track)},
            {"upload": type("UploadStub", (), {"id": 11, "pilot_id": 2})(), "evaluation": evaluate_task(task, task_points, track)},
        ],
        {2: [ScorePenalty(penalty_type="fixed", value=5, reason="Late report", position=0)]},
        event,
        {1: "modern_topless", 2: "single_surface"},
    )
    by_pilot = {row["pilot_id"]: row for row in scored}
    handicap = by_pilot[2]["details_json"]["handicap"]

    assert handicap["adjusted_score_points"] == round(by_pilot[2]["raw_score_points"] * 1.2, 1)
    assert handicap["adjustment_points"] == round(handicap["adjusted_score_points"] - by_pilot[2]["raw_score_points"], 1)
    assert by_pilot[2]["score_points"] == round(max(handicap["adjusted_score_points"] - 5, 0), 2)
    assert by_pilot[2]["rank"] == 1
    assert scored[0]["pilot_id"] == 2


def test_handicap_config_requires_all_positive_multipliers() -> None:
    with pytest.raises(ValueError, match="single_surface"):
        validate_handicap_config({
            "handicap": {
                "enabled": True,
                "multipliers": {
                    "modern_topless": 1,
                    "high_performance_kingpost": 1,
                    "intermediate_kingpost": 1,
                    "single_surface": 0,
                },
            }
        })
