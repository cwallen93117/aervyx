from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventTurnpointSlot, Task, TaskPoint, Turnpoint, TurnpointSource
from app.routers.tasks import _task_response


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_task_response_filters_stale_turnpoints_when_slots_are_active() -> None:
    session = _session()
    event = Event(
        name="Test Event",
        location="Ridgeline",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 20),
        timezone="America/New_York",
    )
    session.add(event)
    session.flush()

    active_source = TurnpointSource(
        event_id=event.id,
        filename="east.gpx",
        content_type="application/gpx+xml",
        file_format="gpx",
        sha256="a" * 64,
        stored_path="/tmp/east.gpx",
    )
    stale_source = TurnpointSource(
        event_id=event.id,
        filename="west.gpx",
        content_type="application/gpx+xml",
        file_format="gpx",
        sha256="b" * 64,
        stored_path="/tmp/west.gpx",
    )
    session.add_all([active_source, stale_source])
    session.flush()

    session.add(EventTurnpointSlot(event_id=event.id, slot_number=1, source_id=active_source.id))

    active_turnpoint = Turnpoint(
        event_id=event.id,
        source_id=active_source.id,
        code="EAST",
        name="East Ridge",
        latitude=38.0,
        longitude=-75.0,
    )
    stale_turnpoint = Turnpoint(
        event_id=event.id,
        source_id=stale_source.id,
        code="WEST",
        name="West Ridge",
        latitude=36.7,
        longitude=-118.2,
    )
    session.add_all([active_turnpoint, stale_turnpoint])
    session.flush()

    task = Task(event_id=event.id, name="Task 1")
    session.add(task)
    session.flush()
    session.add_all(
        [
            TaskPoint(
                task_id=task.id,
                position=1,
                point_type="turnpoint",
                radius_m=400,
                turnpoint_id=stale_turnpoint.id,
                name=stale_turnpoint.name,
                latitude=stale_turnpoint.latitude,
                longitude=stale_turnpoint.longitude,
            ),
            TaskPoint(
                task_id=task.id,
                position=2,
                point_type="turnpoint",
                radius_m=400,
                turnpoint_id=active_turnpoint.id,
                name=active_turnpoint.name,
                latitude=active_turnpoint.latitude,
                longitude=active_turnpoint.longitude,
            ),
            TaskPoint(
                task_id=task.id,
                position=3,
                point_type="goal",
                radius_m=200,
                turnpoint_id=None,
                name="Manual Goal",
                latitude=38.1,
                longitude=-75.1,
            ),
        ]
    )
    session.commit()

    response = _task_response(session, task)

    assert [point.name for point in response.points] == ["East Ridge", "Manual Goal"]
    assert response.task_type == "race"
    assert response.start_gate_count == 1


def test_task_response_preserves_all_points_without_active_slots() -> None:
    session = _session()
    event = Event(
        name="Legacy Event",
        location="Owens Valley",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/Los_Angeles",
    )
    session.add(event)
    session.flush()

    legacy_turnpoint = Turnpoint(
        event_id=event.id,
        source_id=None,
        code="LCH",
        name="Launch Ridge",
        latitude=36.606,
        longitude=-118.062,
    )
    session.add(legacy_turnpoint)
    session.flush()

    task = Task(
        event_id=event.id,
        name="Task 1",
        task_type="speedrun_interval",
        task_start_time="13:30:00",
        task_finish_time="17:45:00",
        start_open_time="14:00:00",
        start_close_time="16:00:00",
        start_gate_count=3,
        start_gate_interval_seconds=900,
    )
    session.add(task)
    session.flush()
    session.add(
        TaskPoint(
            task_id=task.id,
            position=1,
            point_type="launch",
            radius_m=300,
            turnpoint_id=legacy_turnpoint.id,
            name=legacy_turnpoint.name,
            latitude=legacy_turnpoint.latitude,
            longitude=legacy_turnpoint.longitude,
        )
    )
    session.commit()

    response = _task_response(session, task)

    assert [point.name for point in response.points] == ["Launch Ridge"]
    assert response.task_type == "speedrun_interval"
    assert response.task_start_time == "13:30:00"
    assert response.task_finish_time == "17:45:00"
    assert response.start_open_time == "14:00:00"
    assert response.start_close_time == "16:00:00"
    assert response.start_gate_count == 3
    assert response.start_gate_interval_seconds == 900
