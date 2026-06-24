import asyncio
import io
from datetime import date, datetime as dt, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile

from app.db import Base
from app.models import Event, EventPilot, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, ScoreResult, Task, TaskScoringInput, TrackPoint, User
from app.routers import uploads as uploads_router
from app.routers.uploads import _match_pilot_candidate_for_upload, _match_pilot_for_upload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_match_pilot_for_upload_requires_filename_confirmation_for_header_name() -> None:
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
    candidate = _match_pilot_candidate_for_upload(
        session,
        event.id,
        "random-track.igc",
        {"pilot_name": "Charles Allen"},
    )

    assert matched is None
    assert candidate.pilot is not None
    assert candidate.pilot.id == pilot.id
    assert candidate.confidence == "review"


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


def test_match_pilot_for_upload_uses_full_name_inside_timestamped_filename() -> None:
    session = _session()
    event = Event(name="Filename Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    rich = Pilot(first_name="Rich", last_name="Reinauer", email="rich@example.com", competition_number="737")
    other_rich = Pilot(first_name="Rich", last_name="Other", email="other@example.com", competition_number="738")
    session.add_all([event, rich, other_rich])
    session.flush()
    session.add_all([
        EventPilot(event_id=event.id, pilot_id=rich.id),
        EventPilot(event_id=event.id, pilot_id=other_rich.id),
    ])
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "Rich_Reinauer.1748889288000.7028.igc",
        {},
    )

    assert matched is not None
    assert matched.id == rich.id


def test_match_pilot_for_upload_conflicting_header_is_review_only() -> None:
    session = _session()
    event = Event(name="Review Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    rich = Pilot(first_name="Rich", last_name="Reinauer", email="rich@example.com", competition_number="737")
    robin = Pilot(first_name="Robin", last_name="Hamilton", email="robin@example.com", competition_number="99")
    session.add_all([event, rich, robin])
    session.flush()
    session.add_all([
        EventPilot(event_id=event.id, pilot_id=rich.id),
        EventPilot(event_id=event.id, pilot_id=robin.id),
    ])
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "Rich_Reinauer.1748889288000.7028.igc",
        {"pilot_name": "Robin Hamilton"},
    )
    candidate = _match_pilot_candidate_for_upload(
        session,
        event.id,
        "Rich_Reinauer.1748889288000.7028.igc",
        {"pilot_name": "Robin Hamilton"},
    )

    assert matched is None
    assert candidate.pilot is not None
    assert candidate.pilot.id == rich.id
    assert candidate.confidence == "review"


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


def test_single_upload_auto_selects_only_when_no_upload_is_selected(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    pilot = pilots[0]
    rescore_calls: list[int] = []
    monkeypatch.setattr(uploads_router, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(uploads_router, "_publish", lambda task_id, payload: None)
    monkeypatch.setattr(uploads_router, "rescore_task", lambda active_session, task_id: rescore_calls.append(task_id) or [])

    first = asyncio.run(uploads_router.upload_igc(
        task.id,
        _upload_file("first.igc", _igc_content("Charles Allen", 1)),
        pilot.id,
        "manual",
        admin,
        session,
    ))
    second = asyncio.run(uploads_router.upload_igc(
        task.id,
        _upload_file("second.igc", _igc_content("Charles Allen", 2)),
        pilot.id,
        "manual",
        admin,
        session,
    ))

    scoring_input = session.scalar(select(TaskScoringInput).where(
        TaskScoringInput.task_id == task.id,
        TaskScoringInput.pilot_id == pilot.id,
    ))
    assert scoring_input is not None
    assert scoring_input.selected_upload_id == first.id
    assert second.id != first.id
    assert rescore_calls == [task.id]


def test_bulk_upload_review_candidate_is_uploaded_but_not_selected(monkeypatch, tmp_path) -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    rescore_calls: list[int] = []
    monkeypatch.setattr(uploads_router, "get_settings", lambda: SimpleNamespace(max_upload_size_mb=10, upload_root=str(tmp_path)))
    monkeypatch.setattr(uploads_router, "_publish", lambda task_id, payload: None)
    monkeypatch.setattr(uploads_router, "rescore_task", lambda active_session, task_id: rescore_calls.append(task_id) or [])

    result = asyncio.run(uploads_router.bulk_upload_igc(
        task.id,
        [
            _upload_file(
                f"{pilots[0].first_name}_{pilots[0].last_name}.igc",
                _igc_content(f"{pilots[1].first_name} {pilots[1].last_name}", 8),
            )
        ],
        admin,
        session,
    ))[0]

    assert result.matched is False
    assert result.match_confidence == "review"
    assert result.upload_id is not None
    assert result.pilot_id == pilots[0].id
    assert "not auto-selected" in result.message
    assert session.scalar(select(func.count(IGCUpload.id))) == 1
    assert session.scalars(select(TaskScoringInput).where(TaskScoringInput.task_id == task.id)).all() == []
    assert rescore_calls == []


def test_upload_track_geojson_marks_igc_solid() -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    upload = IGCUpload(
        event_id=task.event_id,
        task_id=task.id,
        pilot_id=pilots[0].id,
        uploaded_by_user_id=admin.id,
        filename="solid.igc",
        sha256="def456",
        stored_path="/tmp/solid.igc",
        metadata_json={},
    )
    session.add(upload)
    session.flush()
    session.add_all([
        TrackPoint(upload_id=upload.id, sequence=1, recorded_at=dt(2026, 1, 1, 12, 0, tzinfo=timezone.utc), latitude=36.1, longitude=-118.1, pressure_altitude_m=1000, gps_altitude_m=1000),
        TrackPoint(upload_id=upload.id, sequence=2, recorded_at=dt(2026, 1, 1, 12, 1, tzinfo=timezone.utc), latitude=36.2, longitude=-118.2, pressure_altitude_m=1100, gps_altitude_m=1100),
    ])
    session.commit()

    payload = uploads_router.get_track_geojson(upload.id, user=admin, session=session)

    properties = payload["features"][0]["properties"]
    assert properties["line_style"] == "solid"
    assert properties["track_kind"] == "igc"


def test_delete_upload_keeps_linked_logbook_flight_replayable(tmp_path) -> None:
    session = _session()
    admin, task, pilots = _bulk_upload_fixture(session)
    pilot = pilots[0]
    stored_path = tmp_path / "task-upload.igc"
    stored_path.write_bytes(_igc_content("Charles Allen", 1))
    upload = IGCUpload(
        event_id=task.event_id,
        task_id=task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=admin.id,
        filename="task-upload.igc",
        sha256="abc123",
        stored_path=str(stored_path),
        metadata_json={"flight_date": str(task.task_date)},
    )
    session.add(upload)
    session.flush()
    session.add_all([
        TrackPoint(upload_id=upload.id, sequence=1, recorded_at=dt(2026, 1, 1, 12, 0, tzinfo=timezone.utc), latitude=36.1, longitude=-118.1, pressure_altitude_m=1000, gps_altitude_m=1000),
        TrackPoint(upload_id=upload.id, sequence=2, recorded_at=dt(2026, 1, 1, 12, 1, tzinfo=timezone.utc), latitude=36.2, longitude=-118.2, pressure_altitude_m=1100, gps_altitude_m=1100),
    ])
    scoring_input = TaskScoringInput(task_id=task.id, pilot_id=pilot.id, selected_upload_id=upload.id)
    flight = PilotFlight(
        pilot_id=pilot.id,
        source_kind="task_upload",
        event_id=task.event_id,
        task_id=task.id,
        igc_upload_id=upload.id,
        flight_date=task.task_date,
        site_name="Task site",
        filename=upload.filename,
        sha256=upload.sha256,
        stored_path=upload.stored_path,
        metadata_json={},
    )
    session.add_all([scoring_input, flight, ScoreResult(task_id=task.id, pilot_id=pilot.id, upload_id=upload.id, score_points=100)])
    session.commit()

    result = uploads_router.delete_upload(upload.id, admin, session)

    assert result == {"status": "deleted", "upload_id": upload.id}
    assert session.get(IGCUpload, upload.id) is None
    assert stored_path.exists()
    session.refresh(flight)
    assert flight.igc_upload_id is None
    assert flight.stored_path == str(stored_path)
    assert session.scalar(select(func.count(PilotFlightTrackPoint.id)).where(PilotFlightTrackPoint.flight_id == flight.id)) == 2
    session.refresh(scoring_input)
    assert scoring_input.selected_upload_id is None
