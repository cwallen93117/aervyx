from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import DriverAssignment, Event, LivePosition, MeshDevice, Pilot, Task, TrackingSession, User
from app.routers.auth import update_preferences
from app.routers.public import public_event_positions
from app.routers.tracking import PositionPayload, get_active_task, post_position
from app.schemas import AccountPreferencesUpdate
from app.services.tracking import get_all_active_positions, get_all_recent_positions, get_live_positions, store_position


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _active_task_with_driver(session: Session) -> tuple[Task, User, Pilot]:
    event = Event(
        name="Driver Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 3),
        timezone="UTC",
        is_public_tracking=True,
    )
    pilot = Pilot(first_name="Pat", last_name="Pilot", email="pat@example.com")
    driver = User(
        username="driver@example.com",
        full_name="Dana Driver",
        role="pilot",
        profile_type="driver",
    )
    session.add_all([event, pilot, driver])
    session.flush()
    task = Task(event_id=event.id, name="Active task", status="active", task_date=date(2026, 5, 2))
    session.add(task)
    session.flush()
    session.add(DriverAssignment(task_id=task.id, driver_user_id=driver.id, pilot_id=pilot.id))
    session.commit()
    return task, driver, pilot


def test_mobile_preferences_updates_profile_and_units_without_full_settings_form() -> None:
    session = _session()
    user = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
        altitude_unit="ft",
    )
    session.add(user)
    session.commit()

    response = update_preferences(
        AccountPreferencesUpdate(profile_type="driver", altitude_unit="m"),
        user,
        session,
    )

    session.refresh(user)
    assert response.profile_type == "driver"
    assert response.altitude_unit == "m"
    assert user.profile_type == "driver"
    assert user.altitude_unit == "m"


def test_driver_active_task_prefers_driver_assignment_for_non_pilot_account() -> None:
    session = _session()
    task, driver, _pilot = _active_task_with_driver(session)

    response = get_active_task(driver, session)

    assert response is not None
    assert response.task_id == task.id
    assert response.task_name == "Active task"


def test_driver_app_position_uses_user_subject_without_pilot_or_igc_identity() -> None:
    session = _session()
    task, driver, _pilot = _active_task_with_driver(session)

    response = post_position(
        PositionPayload(lat=35.1, lon=-82.5, alt=900, speed=0, source="app"),
        driver,
        session,
    )

    position = session.scalar(select(LivePosition))
    tracking = session.scalar(select(TrackingSession))
    assert response.subject_key == f"user:{driver.id}"
    assert response.user_id == driver.id
    assert response.pilot_id is None
    assert response.task_id == task.id
    assert response.profile_type == "driver"
    assert position is not None
    assert position.user_id == driver.id
    assert position.pilot_id is None
    assert tracking is not None
    assert tracking.user_id == driver.id
    assert tracking.pilot_id is None


def test_live_queries_and_public_event_positions_include_driver_subjects() -> None:
    session = _session()
    task, driver, _pilot = _active_task_with_driver(session)
    now = datetime.now(UTC)

    store_position(
        session,
        task_id=task.id,
        user_id=driver.id,
        pilot_id=None,
        lat=35.2,
        lon=-82.6,
        alt=700,
        speed=12,
        timestamp=now,
        source="app",
    )
    session.commit()

    task_rows = get_live_positions(session, task.id)
    active_rows = get_all_active_positions(session, minutes=10)
    public_rows = public_event_positions(task.event_id, minutes=60, limit=100, session=session)

    for row in (task_rows[0], active_rows[0], public_rows[0].model_dump()):
        assert row["subject_key"] == f"user:{driver.id}"
        assert row["user_id"] == driver.id
        assert row["pilot_id"] is None
        assert row["pilot_name"] == "Dana Driver"
        assert row["profile_type"] == "driver"


def test_driver_mesh_device_positions_are_classified_as_driver_subjects() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot")
    session.add(owner)
    session.flush()
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="!driver01",
            label="Driver Car",
            purpose="driver_wifi",
            is_active=True,
        )
    )
    session.add(
        LivePosition(
            device_id="!driver01",
            lat=35.0,
            lon=-82.0,
            timestamp=datetime.now(UTC) - timedelta(minutes=1),
            source="mqtt_gateway",
        )
    )
    session.commit()

    rows = get_all_recent_positions(session, minutes=10)

    assert len(rows) == 1
    assert rows[0]["subject_key"] == "device:!driver01"
    assert rows[0]["pilot_name"] == "Driver Car"
    assert rows[0]["profile_type"] == "driver"
    assert rows[0]["position_source"] == "mesh"
