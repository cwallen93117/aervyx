from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import AirspaceRegion, AirspaceSource, Event, EventPilot, IGCUpload, Pilot, ScoreResult, Task, TaskPoint, Turnpoint, TurnpointSource, User
from app.routers.events import _event_payload, duplicate_event


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_event_payload_includes_default_start_gate_settings() -> None:
    session = _session()
    event = Event(
        name="Gate Defaults",
        location="Florida",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
        default_start_gate_count=5,
        default_start_gate_interval_seconds=900,
    )
    session.add(event)
    session.commit()

    payload = _event_payload(session, event)

    assert payload.default_start_gate_count == 5
    assert payload.default_start_gate_interval_seconds == 900


def test_duplicate_event_copies_setup_without_scores(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Sky", last_name="Walker", email="sky@example.com")
    event = Event(
        name="Highland Challenge",
        location="Maryland",
        starts_on=date(2026, 5, 18),
        ends_on=date(2026, 5, 24),
        timezone="America/New_York",
        scoring_formula="GAP2021",
        default_start_gate_count=4,
        default_start_gate_interval_seconds=600,
    )
    session.add_all([admin, pilot, event])
    session.flush()

    source_file = tmp_path / "waypoints.gpx"
    source_file.write_text("<gpx />", encoding="utf-8")
    turnpoint_source = TurnpointSource(
        event_id=event.id,
        filename="waypoints.gpx",
        content_type="application/gpx+xml",
        file_format="gpx",
        sha256="a" * 64,
        stored_path=str(source_file),
        enabled=True,
    )
    session.add(turnpoint_source)
    session.flush()

    turnpoint = Turnpoint(
        event_id=event.id,
        source_id=turnpoint_source.id,
        code="MYLES",
        name="Myles Airport",
        latitude=39.09639,
        longitude=-75.89061,
        elevation_m=22,
    )
    session.add(turnpoint)
    session.flush()

    airspace_file = tmp_path / "airspace.txt"
    airspace_file.write_text("AC D", encoding="utf-8")
    airspace_source = AirspaceSource(
        event_id=event.id,
        kind="airspace",
        filename="airspace.txt",
        content_type="text/plain",
        file_format="openair",
        sha256="b" * 64,
        stored_path=str(airspace_file),
        enabled=True,
    )
    session.add(airspace_source)
    session.flush()
    session.add(
        AirspaceRegion(
            event_id=event.id,
            source_id=airspace_source.id,
            name="Dover D",
            class_code="D",
            type_code="CTR",
            display_category="D",
            geometry_json={"type": "Polygon", "coordinates": []},
            is_restricted_field=False,
        )
    )
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.flush()

    task = Task(
        event_id=event.id,
        name="Task 1",
        status="published",
        task_type="race_to_goal",
        task_start_time="13:30:00",
    )
    session.add(task)
    session.flush()
    session.add(
        TaskPoint(
            task_id=task.id,
            position=1,
            point_type="start",
            direction="exit",
            radius_m=5000,
            turnpoint_id=turnpoint.id,
            name=turnpoint.name,
            latitude=turnpoint.latitude,
            longitude=turnpoint.longitude,
        )
    )
    session.flush()

    upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=admin.id,
        filename="track.igc",
        sha256="c" * 64,
        stored_path=str(tmp_path / "track.igc"),
        metadata_json={},
    )
    session.add(upload)
    session.flush()
    session.add(
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            upload_id=upload.id,
            status="scored",
            score_points=850,
            details_json={},
        )
    )
    session.commit()

    duplicated = duplicate_event(event.id, admin, session)

    assert duplicated.name == "Highland Challenge Duplicate"
    assert duplicated.pilot_count == 1
    assert duplicated.task_count == 1
    assert duplicated.turnpoint_count == 1
    assert duplicated.airspace_count == 1

    duplicated_event = session.get(Event, duplicated.id)
    assert duplicated_event is not None
    assert duplicated_event.default_start_gate_count == 4
    assert duplicated_event.default_start_gate_interval_seconds == 600

    duplicated_turnpoint_source = session.scalar(select(TurnpointSource).where(TurnpointSource.event_id == duplicated.id))
    assert duplicated_turnpoint_source is not None
    assert duplicated_turnpoint_source.stored_path != str(source_file)
    assert Path(duplicated_turnpoint_source.stored_path).exists()

    duplicated_turnpoint = session.scalar(select(Turnpoint).where(Turnpoint.event_id == duplicated.id))
    assert duplicated_turnpoint is not None
    assert duplicated_turnpoint.name == "Myles Airport"

    duplicated_task = session.scalar(select(Task).where(Task.event_id == duplicated.id))
    assert duplicated_task is not None
    assert duplicated_task.name == "Task 1"
    assert duplicated_task.task_type == "race_to_goal_with_gates"

    duplicated_task_point = session.scalar(select(TaskPoint).where(TaskPoint.task_id == duplicated_task.id))
    assert duplicated_task_point is not None
    assert duplicated_task_point.turnpoint_id == duplicated_turnpoint.id
    assert duplicated_task_point.direction == "exit"

    assert session.scalar(select(EventPilot).where(EventPilot.event_id == duplicated.id, EventPilot.pilot_id == pilot.id)) is not None
    assert session.scalar(select(IGCUpload).where(IGCUpload.event_id == duplicated.id)) is None
    assert session.scalar(select(ScoreResult).join(Task, Task.id == ScoreResult.task_id).where(Task.event_id == duplicated.id)) is None
