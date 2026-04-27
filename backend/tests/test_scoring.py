from datetime import UTC, datetime

import pytest

from app.models import Task, TaskPoint, TrackPoint
from app.services.scoring import _build_airscore_pilot_result, _build_formula, _compute_optimized_task_distance, _score_evaluations, evaluate_task


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
    assert result["started_at"] == datetime(2025, 6, 2, 17, 30, tzinfo=UTC)
    assert result["goal_at"] == track_points[3].recorded_at


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


def test_goal_ss_penalty_preserves_explicit_zero() -> None:
    event = type("EventStub", (), {"goal_ss_penalty": 0.0})()

    formula = _build_formula(_task(), event)

    assert formula["sspenalty"] == 0.0


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
    assert result["distance_flown_km"] < 55


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
