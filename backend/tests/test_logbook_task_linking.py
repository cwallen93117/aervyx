import asyncio
from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventPilot, IGCUpload, Pilot, PilotFlight, ScoreResult, Task, TaskScoringInput, TrackPoint, User
from app.services import task_uploads
from app.services.logbook import create_app_upload_flight


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _igc_content(pilot_name: str = "Alex Pilot") -> bytes:
    return (
        "AXXX\n"
        "HFDTE010126\n"
        f"HFPLTPILOTINCHARGE:{pilot_name}\n"
        "B1200003612345N11812345WA0123401234\n"
        "B1201003612445N11812445WA0123501235\n"
    ).encode()


def _user_with_task(session: Session, *, task_date: date = date(2026, 1, 1)) -> tuple[User, Task]:
    pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com", competition_number="12")
    user = User(username="alex", full_name="Alex Pilot", role="pilot", profile_type="pilot", pilot_id=None)
    event = Event(name="HC 2026", location="Myles", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 7), timezone="UTC")
    session.add_all([pilot, user, event])
    session.flush()
    user.pilot_id = pilot.id
    task = Task(event_id=event.id, name="Practice Day", task_date=task_date, status="published")
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.commit()
    return user, task


def _patch_task_upload_runtime(monkeypatch, tmp_path, rescore_calls: list[int] | None = None) -> None:
    monkeypatch.setattr(task_uploads, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(task_uploads, "_publish", lambda task_id, payload: None)
    if rescore_calls is not None:
        monkeypatch.setattr(task_uploads, "rescore_task", lambda active_session, task_id: rescore_calls.append(task_id) or [])


def test_logbook_upload_same_day_task_creates_task_upload_and_scores(monkeypatch, tmp_path) -> None:
    session = _session()
    user, task = _user_with_task(session)
    rescore_calls: list[int] = []
    session.add(ScoreResult(task_id=task.id, pilot_id=user.pilot_id, score_points=25))
    session.commit()
    _patch_task_upload_runtime(monkeypatch, tmp_path, rescore_calls)

    flight = asyncio.run(create_app_upload_flight(
        session,
        user=user,
        filename="Charles_Allen.igc",
        content=_igc_content(),
    ))
    session.commit()

    assert flight.source_kind == "task_upload"
    assert flight.event_id == task.event_id
    assert flight.task_id == task.id
    assert flight.igc_upload_id is not None
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    assert session.scalar(select(func.count(TrackPoint.id))) == 2
    scoring_input = session.scalar(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id, TaskScoringInput.pilot_id == user.pilot_id))
    assert scoring_input is not None
    assert scoring_input.selected_upload_id == flight.igc_upload_id
    assert rescore_calls == [task.id]


def test_logbook_upload_duplicate_same_day_task_reuses_existing_upload(monkeypatch, tmp_path) -> None:
    session = _session()
    user, task = _user_with_task(session)
    _patch_task_upload_runtime(monkeypatch, tmp_path)

    first = asyncio.run(create_app_upload_flight(session, user=user, filename="Charles_Allen.igc", content=_igc_content()))
    second = asyncio.run(create_app_upload_flight(session, user=user, filename="Charles_Allen.igc", content=_igc_content()))
    session.commit()

    assert first.id == second.id
    assert first.igc_upload_id == second.igc_upload_id
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    assert session.scalar(select(func.count(TrackPoint.id))) == 2
    assert session.scalar(select(func.count(PilotFlight.id))) == 1
    assert session.get(Task, task.id) is not None


def test_logbook_upload_without_same_day_task_stays_logbook_only(monkeypatch, tmp_path) -> None:
    session = _session()
    user, _task = _user_with_task(session, task_date=date(2026, 1, 2))
    _patch_task_upload_runtime(monkeypatch, tmp_path)

    flight = asyncio.run(create_app_upload_flight(session, user=user, filename="Charles_Allen.igc", content=_igc_content()))
    session.commit()

    assert flight.source_kind == "app_upload"
    assert flight.event_id is None
    assert flight.task_id is None
    assert flight.igc_upload_id is None
    assert session.scalar(select(func.count(IGCUpload.id))) == 0
    assert flight.metadata_json.get("task_link_status") is None


def test_logbook_upload_with_multiple_same_day_tasks_stays_logbook_only_with_ambiguous_metadata(monkeypatch, tmp_path) -> None:
    session = _session()
    user, task = _user_with_task(session)
    second_event = Event(name="HC 2026 Duplicate", location="Myles", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 7), timezone="UTC")
    session.add(second_event)
    session.flush()
    second_task = Task(event_id=second_event.id, name="Practice Day Copy", task_date=task.task_date, status="published")
    session.add_all([second_task, EventPilot(event_id=second_event.id, pilot_id=user.pilot_id)])
    session.commit()
    _patch_task_upload_runtime(monkeypatch, tmp_path)

    flight = asyncio.run(create_app_upload_flight(session, user=user, filename="Charles_Allen.igc", content=_igc_content()))
    session.commit()

    assert flight.source_kind == "app_upload"
    assert flight.igc_upload_id is None
    assert session.scalar(select(func.count(IGCUpload.id))) == 0
    assert flight.metadata_json["task_link_status"] == "ambiguous"
    assert flight.metadata_json["task_link_candidate_ids"] == [task.id, second_task.id]


def test_logbook_upload_with_multiple_same_day_tasks_uses_active_task(monkeypatch, tmp_path) -> None:
    session = _session()
    user, task = _user_with_task(session)
    task.status = "active"
    second_event = Event(name="HC 2026 Duplicate", location="Myles", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 7), timezone="UTC")
    session.add(second_event)
    session.flush()
    second_task = Task(event_id=second_event.id, name="Practice Day Copy", task_date=task.task_date, status="published")
    session.add_all([second_task, EventPilot(event_id=second_event.id, pilot_id=user.pilot_id)])
    session.add(ScoreResult(task_id=task.id, pilot_id=user.pilot_id, score_points=25))
    session.commit()
    rescore_calls: list[int] = []
    _patch_task_upload_runtime(monkeypatch, tmp_path, rescore_calls)

    flight = asyncio.run(create_app_upload_flight(session, user=user, filename="Charles_Allen.igc", content=_igc_content()))
    session.commit()

    assert flight.source_kind == "task_upload"
    assert flight.task_id == task.id
    assert flight.igc_upload_id is not None
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    scoring_input = session.scalar(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id, TaskScoringInput.pilot_id == user.pilot_id))
    assert scoring_input is not None
    assert scoring_input.selected_upload_id == flight.igc_upload_id
    assert rescore_calls == [task.id]
