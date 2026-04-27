import asyncio
import io
from datetime import date
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile

from app.db import Base
from app.models import Event, EventPilot, IGCUpload, Pilot, Task, TaskScoringInput, User
from app.routers import uploads as uploads_router
from app.routers.uploads import _match_pilot_for_upload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_match_pilot_for_upload_uses_header_name() -> None:
    session = _session()
    event = Event(name="Header Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com", competition_number="12")
    session.add_all([event, pilot])
    session.flush()
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "random-track.igc",
        {"pilot_name": "Charles Allen"},
    )

    assert matched is not None
    assert matched.id == pilot.id


def test_match_pilot_for_upload_uses_filename_when_header_missing() -> None:
    session = _session()
    event = Event(name="Filename Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    pilot = Pilot(first_name="Cory", last_name="Barnwell", email="cory@example.com", competition_number="27")
    session.add_all([event, pilot])
    session.flush()
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "Cory_Barnwell.1748889288000.7028.igc",
        {},
    )

    assert matched is not None
    assert matched.id == pilot.id


def _igc_content(pilot_name: str, second: int) -> bytes:
    return (
        f"AXXX\n"
        f"HFDTE010126\n"
        f"HFPLTPILOTINCHARGE:{pilot_name}\n"
        f"B1200{second:02d}3612345N11812345WA0123401234\n"
        f"B1201{second:02d}3612445N11812445WA0123501235\n"
    ).encode()


def _upload_file(filename: str, content: bytes) -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


def _bulk_upload_fixture(session: Session) -> tuple[User, Task, list[Pilot]]:
    admin = User(username="admin", full_name="Admin", role="admin", profile_type="organizer")
    event = Event(name="FL 2026 comp", location="Florida", starts_on=date(2026, 1, 1), ends_on=date(2026, 1, 10), timezone="UTC")
    session.add_all([admin, event])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", task_date=date(2026, 1, 1), status="published")
    session.add(task)
    session.flush()
    pilots = [
        Pilot(first_name="Charles", last_name="Allen", email="charles@example.com", competition_number="12"),
        Pilot(first_name="Cory", last_name="Barnwell", email="cory@example.com", competition_number="27"),
    ]
    for pilot in pilots:
        session.add(pilot)
        session.flush()
        session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()
    return admin, task, pilots


def _bulk_upload_files(pilots: list[Pilot]) -> list[UploadFile]:
    return [
        _upload_file(
            f"{pilot.competition_number}-{pilot.first_name}-{pilot.last_name}.igc",
            _igc_content(f"{pilot.first_name} {pilot.last_name}", index + 1),
        )
        for index, pilot in enumerate(pilots)
    ]


def test_bulk_upload_selects_matched_uploads_and_rescores_once(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    rescore_calls: list[int] = []
    monkeypatch.setattr(uploads_router, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(uploads_router, "_publish", lambda task_id, payload: None)
    monkeypatch.setattr(uploads_router, "rescore_task", lambda active_session, task_id: rescore_calls.append(task_id) or [])

    results = asyncio.run(uploads_router.bulk_upload_igc(task.id, _bulk_upload_files(pilots), admin, session))

    assert [item.matched for item in results] == [True, True]
    assert rescore_calls == [task.id]
    scoring_inputs = session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id)).all()
    assert len(scoring_inputs) == 2
    assert {entry.selected_upload_id for entry in scoring_inputs} == {item.upload_id for item in results}


def test_bulk_upload_duplicate_files_reuse_existing_uploads(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    rescore_calls: list[int] = []
    monkeypatch.setattr(uploads_router, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(uploads_router, "_publish", lambda task_id, payload: None)
    monkeypatch.setattr(uploads_router, "rescore_task", lambda active_session, task_id: rescore_calls.append(task_id) or [])

    first_results = asyncio.run(uploads_router.bulk_upload_igc(task.id, _bulk_upload_files(pilots), admin, session))
    duplicate_results = asyncio.run(uploads_router.bulk_upload_igc(task.id, _bulk_upload_files(pilots), admin, session))

    assert session.scalar(select(func.count(IGCUpload.id))) == 2
    assert [item.upload_id for item in duplicate_results] == [item.upload_id for item in first_results]
    assert all("Already uploaded" in item.message for item in duplicate_results)
    assert rescore_calls == [task.id]
