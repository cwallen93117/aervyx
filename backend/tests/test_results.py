import asyncio
from datetime import date, datetime
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventPilot, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, ScoreResult, Task, TaskScoringInput, TrackPoint, User
from app.routers import results as results_router
from app.routers.results import list_logbook_igc_candidates, select_logbook_igc_candidate, task_result_summary
from app.services import task_uploads


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _score(task: Task, pilot: Pilot, quality: float | None, state: str = "official") -> ScoreResult:
    details_json = {}
    if quality is not None:
        details_json = {"gap": {"validity": {"overall": quality}}}
    return ScoreResult(
        task_id=task.id,
        pilot_id=pilot.id,
        status="goal",
        rank=1,
        distance_flown_km=40,
        raw_score_points=900,
        score_points=900,
        details_json=details_json,
        result_state=state,
    )


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
    session.add_all([
        _score(tasks[0], pilot, 1.0),
        _score(tasks[1], pilot, 0.5805),
        _score(tasks[2], pilot, None),
    ])
    session.flush()

    summaries = task_result_summary(event.id, user=admin, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in summaries] == [
        (tasks[0].id, 1.0),
        (tasks[1].id, 0.5805),
        (tasks[2].id, None),
    ]


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


def _igc_content(pilot_name: str = "Charles Allen") -> bytes:
    return (
        "AXXX\n"
        "HFDTE010126\n"
        f"HFPLTPILOTINCHARGE:{pilot_name}\n"
        "B1200003612345N11812345WA0123401234\n"
        "B1201003612445N11812445WA0123501235\n"
    ).encode()


def _scoring_logbook_fixture(session: Session, tmp_path) -> tuple[User, Pilot, Task, PilotFlight]:
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
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
        metadata_json={"pilot_name": "Charles Allen"},
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
