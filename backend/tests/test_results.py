import asyncio
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventMeetStatsCache, EventPilot, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, ScorePenalty, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint, User
from app.routers import results as results_router
from app.routers.results import get_scoring_operations, get_task_results, list_logbook_igc_candidates, meet_stats, pilot_summary, save_penalties, select_logbook_igc_candidate, task_result_summary
from app.schemas import ScorePenaltySaveRequest
from app.services import task_uploads
from app.services.scoring import MEET_STATS_SCOPE_INTERNAL_ALL, _format_penalty_number, build_cached_meet_stats_payload, invalidate_event_meet_stats_cache, refresh_event_meet_stats_cache


@pytest.fixture(autouse=True)
def _stub_ground_elevation(monkeypatch) -> None:
    monkeypatch.setattr("app.services.scoring.sample_ground_elevation_m", lambda lat, lon: 100.0)
    monkeypatch.setattr("app.services.scoring.queue_event_meet_stats_refresh", lambda *args, **kwargs: None)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_penalty_number_format_uses_thousands_separator() -> None:
    assert _format_penalty_number(1000) == "1,000"
    assert _format_penalty_number(1234.5) == "1,234.5"


def test_save_penalties_rescores_task_total(monkeypatch) -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Mixed Penalty Race", location="Ridge", starts_on=date(2026, 7, 1), ends_on=date(2026, 7, 2), timezone="UTC")
    pilot = Pilot(first_name="Charles", last_name="Allen")
    session.add_all([admin, event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published")
    session.add(task)
    session.flush()
    result = ScoreResult(
        task_id=task.id,
        pilot_id=pilot.id,
        status="partial",
        rank=1,
        raw_score_points=900,
        score_points=1000,
        details_json={"handicap": {"adjusted_score_points": 1000, "adjustment_points": 100}},
        result_state="provisional",
    )
    session.add_all([EventPilot(event_id=event.id, pilot_id=pilot.id), result])
    session.flush()

    def fake_rescore(_session: Session, task_id: int) -> list[ScoreResult]:
        assert task_id == task.id
        result.score_points = 950
        return [result]

    monkeypatch.setattr(results_router, "rescore_task", fake_rescore)
    response = save_penalties(
        task.id,
        pilot.id,
        ScorePenaltySaveRequest(penalties=[{"penalty_type": "fixed", "value": 50, "reason": "Late report", "position": 0}]),
        admin,
        session,
    )

    assert response["rescored_count"] == 1
    assert result.score_points == 950


def _score(task: Task, pilot: Pilot, quality: float | None, state: str = "official", status: str = "goal", points: float = 900) -> ScoreResult:
    details_json = {}
    if quality is not None:
        details_json = {"gap": {"validity": {"overall": quality}}}
    return ScoreResult(
        task_id=task.id,
        pilot_id=pilot.id,
        status=status,
        rank=1,
        distance_flown_km=40,
        raw_score_points=points,
        score_points=points,
        details_json=details_json,
        result_state=state,
    )


def test_task_results_expose_event_class_and_handicap_adjustment() -> None:
    session = _session()
    admin = User(username="handicap-admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Mixed Race", location="Ridge", starts_on=date(2026, 7, 1), ends_on=date(2026, 7, 2), timezone="UTC")
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([admin, event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published")
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id, pilot_class="single_surface")])
    session.flush()
    session.add(
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            status="goal",
            rank=1,
            raw_score_points=800,
            score_points=960,
            details_json={
                "handicap": {
                    "pilot_class": "single_surface",
                    "multiplier": 1.2,
                    "official_score_points": 800,
                    "adjusted_score_points": 960,
                    "adjustment_points": 160,
                }
            },
            result_state="official",
        )
    )
    session.commit()

    result = get_task_results(task.id, admin, session)[0]

    assert result.raw_score_points == 800
    assert result.score_points == 960
    assert result.pilot_class == "single_surface"
    assert result.handicap_multiplier == 1.2
    assert result.handicap_adjustment_points == 160


def _add_meet_stats_fixture(session: Session) -> tuple[Event, User, User]:
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    viewer = User(username="viewer@example.com", full_name="Viewer", role="pilot", password_hash="hash")
    event = Event(
        name="Stats Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="UTC",
    )
    official_pilot = Pilot(first_name="Ada", last_name="Cloud")
    provisional_pilot = Pilot(first_name="Ben", last_name="Thermal")
    session.add_all([admin, viewer, event, official_pilot, provisional_pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 4, 19))
    session.add_all([
        task,
        EventPilot(event_id=event.id, pilot_id=official_pilot.id),
        EventPilot(event_id=event.id, pilot_id=provisional_pilot.id),
    ])
    session.flush()
    session.add_all([
        TaskPoint(task_id=task.id, position=1, point_type="start", direction="exit", radius_m=0, name="Start", latitude=0, longitude=0),
        TaskPoint(task_id=task.id, position=2, point_type="goal", direction="enter", radius_m=0, name="Goal", latitude=0, longitude=0.05),
    ])
    session.flush()
    start = datetime(2026, 4, 19, 14, 0, tzinfo=UTC)
    official_upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=official_pilot.id,
        uploaded_by_user_id=admin.id,
        filename="ada.igc",
        sha256="a" * 64,
        stored_path="/tmp/ada.igc",
    )
    provisional_upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=provisional_pilot.id,
        uploaded_by_user_id=admin.id,
        filename="ben.igc",
        sha256="b" * 64,
        stored_path="/tmp/ben.igc",
    )
    session.add_all([official_upload, provisional_upload])
    session.flush()
    session.add_all([
        TrackPoint(upload_id=official_upload.id, sequence=1, recorded_at=start, latitude=0, longitude=0, gps_altitude_m=400),
        TrackPoint(upload_id=official_upload.id, sequence=2, recorded_at=start + timedelta(minutes=20), latitude=0, longitude=0.005, gps_altitude_m=3),
        TrackPoint(upload_id=official_upload.id, sequence=3, recorded_at=start + timedelta(minutes=40), latitude=0, longitude=0.01, gps_altitude_m=130),
        TrackPoint(upload_id=official_upload.id, sequence=4, recorded_at=start + timedelta(hours=1), latitude=0, longitude=0.02, gps_altitude_m=650),
        TrackPoint(upload_id=official_upload.id, sequence=5, recorded_at=start + timedelta(hours=2), latitude=0, longitude=0.04, gps_altitude_m=700),
        TrackPoint(upload_id=provisional_upload.id, sequence=1, recorded_at=start, latitude=0, longitude=0, gps_altitude_m=450),
        TrackPoint(upload_id=provisional_upload.id, sequence=2, recorded_at=start + timedelta(minutes=30), latitude=0, longitude=0.015, gps_altitude_m=120),
        TrackPoint(upload_id=provisional_upload.id, sequence=3, recorded_at=start + timedelta(hours=1), latitude=0, longitude=0.03, gps_altitude_m=900),
    ])
    session.add_all([
        ScoreResult(
            task_id=task.id,
            pilot_id=official_pilot.id,
            upload_id=official_upload.id,
            status="partial",
            rank=1,
            distance_flown_km=4.0,
            started_at=start,
            elapsed_seconds=None,
            raw_score_points=500,
            score_points=500,
            details_json={"task_stats": {"task_distance": 5.5}},
            result_state="official",
        ),
        ScoreResult(
            task_id=task.id,
            pilot_id=provisional_pilot.id,
            upload_id=provisional_upload.id,
            status="partial",
            rank=2,
            distance_flown_km=3.0,
            started_at=start,
            elapsed_seconds=1800,
            raw_score_points=400,
            score_points=400,
            details_json={"task_stats": {"task_distance": 5.5}},
            result_state="provisional",
        ),
    ])
    session.commit()
    return event, admin, viewer


def test_task_result_summary_returns_day_quality_for_each_scored_task() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Spring Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([admin, event, pilot])
    session.flush()
    tasks = [Task(event_id=event.id, name=f"Task {index}") for index in range(1, 4)]
    session.add_all(tasks)
    session.flush()
    first_score = _score(tasks[0], pilot, 1.0)
    session.add_all([
        first_score,
        _score(tasks[1], pilot, 0.5805),
        _score(tasks[2], pilot, None),
    ])
    first_score.details_json = {
        "gap": {
            "task_stats": {"task_distance": 55.307, "no_of_pilots_flying": 19},
            "available_points": {"distance": 318.654},
            "validity": {"overall": 1.0, "launch": 1},
            "formula": {"weightdist": 0.3838},
            "leading_coefficients": {"minimum": 0.9651},
        }
    }
    session.flush()

    summaries = task_result_summary(event.id, user=admin, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in summaries] == [
        (tasks[0].id, 1.0),
        (tasks[1].id, 0.5805),
        (tasks[2].id, None),
    ]
    assert summaries[0].statistics == {
        "task_distance": 55.307,
        "no_of_pilots_flying": 19,
        "available_points_distance": 318.654,
        "launch_validity": 1,
        "day_quality": 1.0,
        "distance_weight": 0.3838,
        "smallest_leading_coefficient": 0.9651,
    }


def test_task_result_summary_hides_provisional_scores_from_pilots() -> None:
    session = _session()
    viewer = User(username="viewer@example.com", full_name="Viewer", role="pilot", password_hash="hash")
    event = Event(
        name="Public Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([viewer, event, pilot])
    session.flush()
    official_task = Task(event_id=event.id, name="Official Task")
    provisional_task = Task(event_id=event.id, name="Provisional Task")
    session.add_all([official_task, provisional_task])
    session.flush()
    session.add_all([
        _score(official_task, pilot, 0.5536, state="official"),
        _score(provisional_task, pilot, 0.75, state="provisional"),
    ])
    session.flush()

    summaries = task_result_summary(event.id, user=viewer, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in summaries] == [
        (official_task.id, 0.5536),
    ]


def test_meet_stats_returns_event_aggregates_for_admin(monkeypatch) -> None:
    session = _session()
    event, admin, _viewer = _add_meet_stats_fixture(session)
    monkeypatch.setattr("app.services.scoring.sample_ground_elevation_m", lambda lat, lon: 100.0)
    refresh_event_meet_stats_cache(session, event.id)
    session.commit()

    payload = meet_stats(event.id, user=admin, session=session)

    assert payload.total_airtime_seconds == 3 * 3600
    assert payload.average_airtime_seconds == 5400
    assert payload.total_xc_distance_km == 7.0
    assert payload.pilot_count == 2
    assert payload.day_count == 1
    assert payload.flight_count == 2
    assert payload.max_gps_altitude is not None
    assert payload.max_gps_altitude.pilot_name == "Ben Thermal"
    assert payload.max_gps_altitude.value_m == 900
    assert payload.max_gps_altitude.recorded_at == "2026-04-19T15:00:00Z"
    assert payload.max_gps_altitude.task_date == "2026-04-19"
    assert payload.lowest_save is not None
    assert payload.lowest_save.pilot_name == "Ada Cloud"
    assert payload.lowest_save.value_m == 130
    assert payload.lowest_save.recorded_at == "2026-04-19T14:40:00Z"
    assert payload.lowest_save.task_date == "2026-04-19"
    assert payload.lowest_save.latitude == 0
    assert payload.lowest_save.longitude == 0.01
    assert payload.lowest_save.ground_altitude_m == 100
    assert payload.lowest_save.agl_altitude_m == 30
    cache_row = session.scalar(
        select(EventMeetStatsCache).where(
            EventMeetStatsCache.event_id == event.id,
            EventMeetStatsCache.scope == MEET_STATS_SCOPE_INTERNAL_ALL,
        )
    )
    assert cache_row is not None
    assert cache_row.payload_json["total_xc_distance_km"] == 7.0
    assert cache_row.payload_json["schema_version"] == 4


def test_meet_stats_returns_immediately_and_queues_refresh_on_empty_cache(monkeypatch) -> None:
    session = _session()
    event, admin, _viewer = _add_meet_stats_fixture(session)
    queued: list[int] = []
    monkeypatch.setattr("app.services.scoring.queue_event_meet_stats_refresh", lambda event_id, **_kwargs: queued.append(int(event_id)))

    payload = meet_stats(event.id, user=admin, session=session)

    assert payload.total_airtime_seconds == 0
    assert queued == [event.id]
    cache_row = session.scalar(
        select(EventMeetStatsCache).where(
            EventMeetStatsCache.event_id == event.id,
            EventMeetStatsCache.scope == MEET_STATS_SCOPE_INTERNAL_ALL,
        )
    )
    assert cache_row is not None
    assert cache_row.payload_json["cache_status"] == "refreshing"


def test_meet_stats_cache_is_reused_until_invalidated() -> None:
    session = _session()
    event, admin, _viewer = _add_meet_stats_fixture(session)
    refresh_event_meet_stats_cache(session, event.id)
    session.commit()

    first_payload = meet_stats(event.id, user=admin, session=session)
    assert first_payload.total_xc_distance_km == 7.0

    result = session.scalar(select(ScoreResult).where(ScoreResult.result_state == "official"))
    assert result is not None
    result.distance_flown_km = 14.0
    session.commit()

    cached_payload = meet_stats(event.id, user=admin, session=session)
    assert cached_payload.total_xc_distance_km == 7.0

    invalidate_event_meet_stats_cache(session, event.id)
    session.commit()
    stale_payload = meet_stats(event.id, user=admin, session=session)
    assert stale_payload.total_xc_distance_km == 7.0

    refresh_event_meet_stats_cache(session, event.id)
    session.commit()
    recalculated_payload = meet_stats(event.id, user=admin, session=session)
    assert recalculated_payload.total_xc_distance_km == 17.0


def test_meet_stats_refreshes_old_cache_schema() -> None:
    session = _session()
    event, admin, _viewer = _add_meet_stats_fixture(session)
    session.add(
        EventMeetStatsCache(
            event_id=event.id,
            scope=MEET_STATS_SCOPE_INTERNAL_ALL,
            payload_json={"total_airtime_seconds": 1, "total_xc_distance_km": 1.0},
        )
    )
    session.commit()

    payload_dict = build_cached_meet_stats_payload(session, event.id, MEET_STATS_SCOPE_INTERNAL_ALL, result_states={"official", "provisional"}, allow_sync_refresh=True)
    session.commit()

    assert payload_dict["total_airtime_seconds"] == 3 * 3600
    assert payload_dict["average_airtime_seconds"] == 5400
    cache_row = session.scalar(
        select(EventMeetStatsCache).where(
            EventMeetStatsCache.event_id == event.id,
            EventMeetStatsCache.scope == MEET_STATS_SCOPE_INTERNAL_ALL,
        )
    )
    assert cache_row is not None
    assert cache_row.payload_json["schema_version"] == 4
    assert cache_row.payload_json["average_airtime_seconds"] == 5400


def test_meet_stats_skips_bad_low_save_geometry_without_failing() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Bad Geometry Race", location="Ridge", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    pilot = Pilot(first_name="Ada", last_name="Cloud")
    session.add_all([admin, event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add(task)
    session.flush()
    session.add_all([
        TaskPoint(task_id=task.id, position=1, point_type="start", direction="exit", radius_m=0, name="Start", latitude=0, longitude=0),
        TaskPoint(task_id=task.id, position=2, point_type="goal", direction="enter", radius_m=0, name="Bad Goal", latitude=999, longitude=0),
    ])
    start = datetime(2026, 5, 2, 14, 0, tzinfo=UTC)
    upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=admin.id,
        filename="bad.igc",
        sha256="f" * 64,
        stored_path="/tmp/bad.igc",
    )
    session.add(upload)
    session.flush()
    session.add_all([
        TrackPoint(upload_id=upload.id, sequence=1, recorded_at=start, latitude=0, longitude=0, gps_altitude_m=500),
        TrackPoint(upload_id=upload.id, sequence=2, recorded_at=start + timedelta(minutes=30), latitude=999, longitude=0, gps_altitude_m=120),
        TrackPoint(upload_id=upload.id, sequence=3, recorded_at=start + timedelta(hours=1), latitude=0, longitude=0.01, gps_altitude_m=800),
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            upload_id=upload.id,
            status="partial",
            rank=1,
            distance_flown_km=8,
            started_at=start,
            elapsed_seconds=3600,
            raw_score_points=500,
            score_points=500,
            result_state="official",
        ),
    ])
    session.commit()
    refresh_event_meet_stats_cache(session, event.id)
    session.commit()

    payload = meet_stats(event.id, user=admin, session=session)

    assert payload.total_airtime_seconds == 3600
    assert payload.average_airtime_seconds == 3600
    assert payload.total_xc_distance_km == 8
    assert payload.pilot_count == 1
    assert payload.day_count == 1
    assert payload.flight_count == 1
    assert payload.max_gps_altitude is not None
    assert payload.max_gps_altitude.value_m == 800
    assert payload.lowest_save is None


def test_meet_stats_hides_provisional_scores_from_pilots() -> None:
    session = _session()
    event, _admin, viewer = _add_meet_stats_fixture(session)
    refresh_event_meet_stats_cache(session, event.id)
    session.commit()

    payload = meet_stats(event.id, user=viewer, session=session)

    assert payload.total_airtime_seconds == 2 * 3600
    assert payload.average_airtime_seconds == 7200
    assert payload.total_xc_distance_km == 4.0
    assert payload.pilot_count == 1
    assert payload.day_count == 1
    assert payload.flight_count == 1
    assert payload.max_gps_altitude is not None
    assert payload.max_gps_altitude.pilot_name == "Ada Cloud"
    assert payload.max_gps_altitude.value_m == 700
    assert payload.lowest_save is not None
    assert payload.lowest_save.pilot_name == "Ada Cloud"
    assert payload.lowest_save.value_m == 130


def test_task_results_include_penalty_calculation_details() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Penalty Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )

    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([admin, event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1")
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    details_json = {
        "start_timing": {
            "actual_start_crossing_at": "2026-04-18T14:14:30Z",
            "start_gate_index": 2,
            "start_gate_time": "2026-04-18T14:15:00Z",
            "jump_the_gun_seconds": 30,
            "jump_the_gun_penalty_seconds": 30,
            "jump_the_gun_penalty_points": 60,
        },
        "gap": {"formula": {"jump_the_gun_factor": 2}},
    }
    session.add(
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            status="goal",
            rank=1,
            distance_flown_km=40,
            raw_score_points=1000,
            score_points=890,
            details_json=details_json,
            result_state="official",
        )
    )
    session.add_all(
        [
            ScorePenalty(task_id=task.id, pilot_id=pilot.id, penalty_type="percentage", value=10, reason="Cloud flying", position=0),
            ScorePenalty(task_id=task.id, pilot_id=pilot.id, penalty_type="fixed", value=10, reason="Late report", position=1),
        ]
    )
    session.flush()

    payload = get_task_results(task.id, user=admin, session=session)

    result = payload[0]
    assert result.penalty_summary == "Early start penalty -60 pts, -10%, -10 pts"
    assert len(result.penalties) == 2
    assert result.penalty_calculation is not None
    assert result.penalty_calculation.engine_penalty_points == 60
    assert result.penalty_calculation.manual_penalty_points == 110
    assert result.penalty_calculation.total_display_penalty_points == 170
    assert [(line.kind, line.label, line.amount_points) for line in result.penalty_calculation.lines] == [
        ("engine", "Early start penalty", 60.0),
        ("manual", "Cloud flying", 100.0),
        ("manual", "Late report", 10.0),
    ]
    assert result.penalty_calculation.lines[0].detail == "Started at 10:14:30 AM EDT, before start gate 2 at 10:15:00 AM EDT. Early by 30s. Charged 2 points per second."


def test_task_results_sort_minimum_distance_by_points_before_dnf_absent() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Status Sort Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilots = [
        Pilot(first_name="Fast", last_name="Pilot"),
        Pilot(first_name="Minimum", last_name="Distance"),
        Pilot(first_name="Did", last_name="Notfly"),
        Pilot(first_name="Absent", last_name="Pilot"),
        Pilot(first_name="Unscored", last_name="Pilot"),
    ]
    session.add_all([admin, event, *pilots])
    session.flush()
    task = Task(event_id=event.id, name="Task 1")
    session.add(task)
    session.add_all([EventPilot(event_id=event.id, pilot_id=pilot.id) for pilot in pilots])
    session.flush()
    session.add_all([
        ScoreResult(
            task_id=task.id,
            pilot_id=pilots[0].id,
            status="partial",
            rank=1,
            distance_flown_km=12,
            raw_score_points=200,
            score_points=200,
            details_json={},
            result_state="official",
        ),
        ScoreResult(
            task_id=task.id,
            pilot_id=pilots[1].id,
            status="minimum_distance",
            rank=None,
            distance_flown_km=5,
            raw_score_points=140,
            score_points=140,
            details_json={},
            result_state="official",
        ),
        ScoreResult(
            task_id=task.id,
            pilot_id=pilots[2].id,
            status="did_not_fly",
            rank=None,
            distance_flown_km=0,
            raw_score_points=0,
            score_points=0,
            details_json={},
            result_state="official",
        ),
        ScoreResult(
            task_id=task.id,
            pilot_id=pilots[3].id,
            status="absent",
            rank=None,
            distance_flown_km=0,
            raw_score_points=0,
            score_points=0,
            details_json={},
            result_state="official",
        ),
    ])
    session.flush()

    payload = get_task_results(task.id, user=admin, session=session)

    assert [result.pilot_name for result in payload] == [
        "Fast Pilot",
        "Minimum Distance",
        "Did Notfly",
        "Absent Pilot",
        "Unscored Pilot",
    ]


def test_scoring_operations_include_automatic_penalty_summary() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Penalty Ops",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Alex", last_name="Pilot")
    session.add_all([admin, event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Practice Day", status="published")
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=admin.id,
        filename="charles.igc",
        sha256="ops-penalty",
        stored_path="/tmp/charles.igc",
        metadata_json={},
    )
    session.add(upload)
    session.flush()
    session.add(
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            upload_id=upload.id,
            status="goal",
            rank=1,
            distance_flown_km=40,
            raw_score_points=400,
            score_points=400,
            details_json={
                "start_timing": {
                    "actual_start_crossing_at": "2026-04-18T14:09:08Z",
                    "start_gate_index": 1,
                    "start_gate_time": "2026-04-18T14:15:00Z",
                    "jump_the_gun_seconds": 352,
                    "jump_the_gun_penalty_seconds": 300,
                    "jump_the_gun_penalty_points": 600,
                },
                "gap": {"formula": {"jump_the_gun_factor": 2}},
            },
            result_state="provisional",
        )
    )
    session.flush()

    payload = get_scoring_operations(task.id, admin=admin, session=session)

    assert len(payload.rows) == 1
    row = payload.rows[0]
    assert row.penalty_summary == "Early start penalty -600 pts"
    assert row.result is not None
    assert row.result.penalty_calculation is not None
    assert row.result.penalty_calculation.engine_penalty_points == 600
    assert row.result.penalty_calculation.lines[0].detail == "Started at 10:09:08 AM EDT, before start gate 1 at 10:15:00 AM EDT. Early by 5m 52s; penalty was capped at 5m. Charged 2 points per second."


def test_pilot_summary_keeps_practice_scores_out_of_totals() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Practice Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([admin, event, pilot])
    session.flush()
    practice_task = Task(event_id=event.id, name="Practice", is_practice=True)
    competition_task = Task(event_id=event.id, name="Task 1")
    session.add_all([practice_task, competition_task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    session.add_all([
        _score(practice_task, pilot, 1.0),
        _score(competition_task, pilot, 1.0),
    ])
    session.flush()

    summaries = pilot_summary(event.id, user=admin, session=session)

    assert len(summaries) == 1
    assert summaries[0].total_score_points == 900
    assert summaries[0].tasks_scored == 1
    assert summaries[0].task_scores == {practice_task.id: 900, competition_task.id: 900}
    assert summaries[0].task_statuses == {practice_task.id: "goal", competition_task.id: "goal"}


def test_pilot_summary_includes_absent_and_dnf_task_statuses() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Status Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    absent_pilot = Pilot(first_name="Ada", last_name="Absent")
    dnf_pilot = Pilot(first_name="Ben", last_name="Grounded")
    session.add_all([admin, event, absent_pilot, dnf_pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1")
    session.add_all([
        task,
        EventPilot(event_id=event.id, pilot_id=absent_pilot.id),
        EventPilot(event_id=event.id, pilot_id=dnf_pilot.id),
    ])
    session.flush()
    session.add_all([
        _score(task, absent_pilot, 1.0, status="absent", points=0),
        _score(task, dnf_pilot, 1.0, status="did_not_fly", points=0),
    ])
    session.flush()

    summaries = pilot_summary(event.id, user=admin, session=session)
    summaries_by_name = {summary.pilot_name: summary for summary in summaries}

    assert summaries_by_name["Ada Absent"].task_scores == {task.id: 0}
    assert summaries_by_name["Ada Absent"].task_statuses == {task.id: "absent"}
    assert summaries_by_name["Ben Grounded"].task_scores == {task.id: 0}
    assert summaries_by_name["Ben Grounded"].task_statuses == {task.id: "did_not_fly"}


def _igc_content(pilot_name: str = "Alex Pilot") -> bytes:
    return (
        "AXXX\n"
        "HFDTE010126\n"
        f"HFPLTPILOTINCHARGE:{pilot_name}\n"
        "B1200003612345N11812345WA0123401234\n"
        "B1201003612445N11812445WA0123501235\n"
    ).encode()


def _scoring_logbook_fixture(session: Session, tmp_path) -> tuple[User, Pilot, Task, PilotFlight]:
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com")
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 7), timezone="UTC")
    session.add_all([admin, pilot, event])
    session.flush()
    task = Task(event_id=event.id, name="Practice Day", task_date=date(2026, 1, 1), status="published")
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    stored_path = tmp_path / "Charles_Allen.igc"
    stored_path.write_bytes(_igc_content())
    flight = PilotFlight(
        pilot_id=pilot.id,
        source_kind="app_upload",
        event_id=None,
        task_id=None,
        igc_upload_id=None,
        flight_date=date(2026, 1, 1),
        site_name="Myles",
        filename="Charles_Allen.igc",
        sha256="sha",
        stored_path=str(stored_path),
        metadata_json={"pilot_name": "Alex Pilot"},
    )
    session.add(flight)
    session.flush()
    session.add(PilotFlightTrackPoint(
        flight_id=flight.id,
        sequence=1,
        recorded_at=datetime(2026, 1, 1, 12, 0, 0),
        latitude=36,
        longitude=-118,
        pressure_altitude_m=1000,
        gps_altitude_m=1000,
    ))
    session.commit()
    return admin, pilot, task, flight


def _patch_scoring_logbook_runtime(monkeypatch, tmp_path, rescore_calls: list[int] | None = None) -> None:
    monkeypatch.setattr(task_uploads, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(task_uploads, "_publish", lambda task_id, payload: None)
    calls = rescore_calls if rescore_calls is not None else []
    monkeypatch.setattr(results_router, "rescore_task", lambda active_session, task_id: calls.append(task_id) or [])


def test_logbook_candidates_list_same_date_igc_backed_flights(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, pilot, task, flight = _scoring_logbook_fixture(session, tmp_path)
    session.add(PilotFlight(
        pilot_id=pilot.id,
        source_kind="app_upload",
        flight_date=date(2026, 1, 2),
        site_name="Other day",
        filename="other.igc",
        stored_path=str(tmp_path / "missing.igc"),
        metadata_json={},
    ))
    session.add(PilotFlight(
        pilot_id=pilot.id,
        source_kind="manual",
        flight_date=task.task_date,
        site_name="Manual",
        filename=None,
        stored_path=None,
        metadata_json={},
    ))
    session.commit()
    _patch_scoring_logbook_runtime(monkeypatch, tmp_path)

    candidates = list_logbook_igc_candidates(task.id, pilot.id, admin, session)

    assert [candidate.flight_id for candidate in candidates] == [flight.id]
    assert candidates[0].filename == "Charles_Allen.igc"
    assert candidates[0].already_linked_upload_id is None


def test_select_logbook_candidate_imports_selects_and_rescores(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, pilot, task, flight = _scoring_logbook_fixture(session, tmp_path)
    rescore_calls: list[int] = []
    _patch_scoring_logbook_runtime(monkeypatch, tmp_path, rescore_calls)

    response = asyncio.run(select_logbook_igc_candidate(task.id, pilot.id, flight.id, admin, session))

    assert response.selected_upload_id is not None
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    assert session.scalar(select(func.count(TrackPoint.id))) == 2
    scoring_input = session.scalar(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id, TaskScoringInput.pilot_id == pilot.id))
    assert scoring_input is not None
    assert scoring_input.selected_upload_id == response.selected_upload_id
    session.refresh(flight)
    assert flight.source_kind == "task_upload"
    assert flight.igc_upload_id == response.selected_upload_id
    assert session.scalar(select(func.count(PilotFlight.id))) == 1
    assert rescore_calls == [task.id]


def test_select_existing_task_backed_logbook_candidate_does_not_duplicate_upload(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, pilot, task, _flight = _scoring_logbook_fixture(session, tmp_path)
    _patch_scoring_logbook_runtime(monkeypatch, tmp_path)
    first = asyncio.run(select_logbook_igc_candidate(task.id, pilot.id, _flight.id, admin, session))
    session.commit()
    linked_flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == first.selected_upload_id))

    second = asyncio.run(select_logbook_igc_candidate(task.id, pilot.id, linked_flight.id, admin, session))

    assert second.selected_upload_id == first.selected_upload_id
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    assert session.scalar(select(func.count(TrackPoint.id))) == 2


def test_select_logbook_candidate_rejects_wrong_pilot_or_date(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, pilot, task, flight = _scoring_logbook_fixture(session, tmp_path)
    other = Pilot(first_name="Other", last_name="Pilot", email="other@example.com")
    session.add(other)
    session.flush()
    _patch_scoring_logbook_runtime(monkeypatch, tmp_path)

    try:
        asyncio.run(select_logbook_igc_candidate(task.id, other.id, flight.id, admin, session))
    except Exception as exc:
        assert "Pilot not found" in str(exc) or getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Wrong pilot selection should fail")

    flight.flight_date = date(2026, 1, 2)
    session.commit()
    try:
        asyncio.run(select_logbook_igc_candidate(task.id, pilot.id, flight.id, admin, session))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 404
    else:
        raise AssertionError("Wrong-date selection should fail")
