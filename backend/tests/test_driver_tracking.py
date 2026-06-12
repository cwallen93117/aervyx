from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import DriverAssignment, Event, EventPilot, LivePosition, MeshDevice, Pilot, SosAlert, Task, TaskPoint, TrackingSession, User
from app.routers.auth import me, update_preferences
from app.routers.public import public_event_positions
from app.routers.tracking import PositionPayload, SosPayload, get_active_task, list_driver_sos_alerts, post_position, post_sos
from app.schemas import AccountPreferencesUpdate
from app.services.tracking import (
    get_all_active_positions,
    get_all_recent_positions,
    get_live_positions,
    resolve_active_task_id,
    store_position,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def test_driver_sos_endpoint_lists_active_pilot_alerts_for_driver() -> None:
    session = _session()
    _task, driver, pilot = _active_task_with_driver(session)
    pilot_user = User(
        username="pat@example.com",
        full_name="Pat Pilot",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    session.add(pilot_user)
    session.commit()

    created = post_sos(
        SosPayload(
            lat=35.1,
            lon=-82.2,
            alt=900,
            message="Need retrieve help",
            timestamp=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
        ),
        pilot_user,
        session,
    )

    alerts = list_driver_sos_alerts(user=driver, session=session)

    assert [alert.id for alert in alerts] == [created.id]
    assert alerts[0].pilot_id == pilot.id
    assert alerts[0].pilot_name == "Pat Pilot"
    assert alerts[0].message == "Need retrieve help"
    assert alerts[0].status == "active"


def test_driver_sos_endpoint_allows_admin_and_hides_resolved_alerts() -> None:
    session = _session()
    _task, _driver, pilot = _active_task_with_driver(session)
    admin = User(
        username="admin@example.com",
        full_name="Admin User",
        role="admin",
        profile_type="pilot",
    )
    session.add_all(
        [
            admin,
            SosAlert(
                pilot_id=pilot.id,
                lat=35.1,
                lon=-82.2,
                alt=None,
                message="Active",
                timestamp=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
                status="active",
            ),
            SosAlert(
                pilot_id=pilot.id,
                lat=35.2,
                lon=-82.3,
                alt=None,
                message="Resolved",
                timestamp=datetime(2026, 5, 2, 12, 1, tzinfo=UTC),
                status="resolved",
            ),
        ]
    )
    session.commit()

    alerts = list_driver_sos_alerts(user=admin, session=session)

    assert len(alerts) == 1
    assert alerts[0].message == "Active"


def test_driver_sos_endpoint_rejects_non_driver_pilot() -> None:
    session = _session()
    user = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
    )
    session.add(user)
    session.commit()

    try:
        list_driver_sos_alerts(user=user, session=session)
    except HTTPException as exc:
        assert exc.status_code == 403
    else:
        raise AssertionError("Expected non-driver pilot to be rejected")


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
    assert response.profile_type_updated_at is not None
    assert response.altitude_unit == "m"
    assert user.profile_type == "driver"
    assert user.altitude_unit == "m"


def test_me_response_includes_profile_type_timestamp() -> None:
    session = _session()
    updated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    user = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
        profile_type_updated_at=updated_at,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    response = me(user)

    assert _utc(response.profile_type_updated_at) == updated_at


def test_mobile_preferences_newer_profile_timestamp_updates_server() -> None:
    session = _session()
    stored_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    incoming_at = stored_at + timedelta(minutes=5)
    user = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
        profile_type_updated_at=stored_at,
    )
    session.add(user)
    session.commit()

    response = update_preferences(
        AccountPreferencesUpdate(
            profile_type="driver",
            profile_type_updated_at=incoming_at,
        ),
        user,
        session,
    )

    session.refresh(user)
    assert response.profile_type == "driver"
    assert _utc(response.profile_type_updated_at) == incoming_at
    assert user.profile_type == "driver"
    assert _utc(user.profile_type_updated_at) == incoming_at


def test_mobile_preferences_stale_profile_timestamp_is_ignored() -> None:
    session = _session()
    stored_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    stale_at = stored_at - timedelta(hours=1)
    user = User(
        username="driver@example.com",
        full_name="Driver User",
        role="pilot",
        profile_type="driver",
        profile_type_updated_at=stored_at,
    )
    session.add(user)
    session.commit()

    response = update_preferences(
        AccountPreferencesUpdate(
            profile_type="pilot",
            profile_type_updated_at=stale_at,
        ),
        user,
        session,
    )

    session.refresh(user)
    assert response.profile_type == "driver"
    assert _utc(response.profile_type_updated_at) == stored_at
    assert user.profile_type == "driver"
    assert _utc(user.profile_type_updated_at) == stored_at


def test_driver_active_task_prefers_driver_assignment_for_non_pilot_account() -> None:
    session = _session()
    task, driver, _pilot = _active_task_with_driver(session)

    response = get_active_task(driver, session)

    assert response is not None
    assert response.task_id == task.id
    assert response.task_name == "Active task"


def test_pilot_active_task_uses_newest_published_event_task() -> None:
    session = _session()
    today_date = datetime.now(UTC).date()
    event = Event(
        name="Published Comp",
        location="Ridge",
        starts_on=today_date - timedelta(days=1),
        ends_on=today_date + timedelta(days=1),
        timezone="UTC",
        visible_airspace_classes_json=["R", "TFR"],
        show_restricted_fields=False,
    )
    pilot = Pilot(first_name="Charles", last_name="Allen", email="cwalle@example.com")
    session.add_all([event, pilot])
    session.flush()
    user = User(
        username="cwalle@example.com",
        full_name="Charles Allen",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    yesterday = Task(
        event_id=event.id,
        name="Task 1 (Day 2)",
        status="published",
        task_date=today_date - timedelta(days=1),
    )
    today = Task(
        event_id=event.id,
        name="Task 2 (Day 3)",
        status="published",
        task_date=today_date,
    )
    session.add_all([user, yesterday, today, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    turnpoint = TaskPoint(
        task_id=today.id,
        position=1,
        name="Start Gate",
        point_type="start",
        latitude=35.123,
        longitude=-82.456,
        radius_m=750,
    )
    session.add(turnpoint)
    session.commit()

    response = get_active_task(user, session)

    assert response is not None
    assert response.task_id == today.id
    assert response.event_id == event.id
    assert response.task_name == "Task 2 (Day 3)"
    assert response.visible_airspace_classes == ["R", "TFR"]
    assert response.show_restricted_fields is False
    assert response.turnpoints[0].id == str(turnpoint.id)
    assert response.turnpoints[0].type == "start"
    assert response.turnpoints[0].point_type == "start"
    assert response.turnpoints[0].radius == 750
    assert response.turnpoints[0].radius_meters == 750


def test_pilot_active_task_prefers_unpublished_same_day_task_during_comp() -> None:
    session = _session()
    event = Event(
        name="Task Draft Comp",
        location="Ridge",
        starts_on=date(2026, 5, 31),
        ends_on=date(2026, 6, 3),
        timezone="UTC",
    )
    pilot = Pilot(first_name="Charles", last_name="Allen", email="cwalle@example.com")
    session.add_all([event, pilot])
    session.flush()
    yesterday = Task(
        event_id=event.id,
        name="Task 1",
        status="published",
        task_date=date(2026, 6, 1),
    )
    today_draft = Task(
        event_id=event.id,
        name="Task 2 Notes",
        status="draft",
        task_date=date(2026, 6, 2),
    )
    session.add_all([yesterday, today_draft, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.commit()

    task_id = resolve_active_task_id(
        session,
        pilot.id,
        now=datetime(2026, 6, 2, 14, tzinfo=UTC),
    )

    assert task_id == today_draft.id


def test_pilot_active_task_falls_back_to_prior_task_before_comp_ends() -> None:
    session = _session()
    event = Event(
        name="No Draft Comp",
        location="Ridge",
        starts_on=date(2026, 5, 31),
        ends_on=date(2026, 6, 3),
        timezone="UTC",
    )
    pilot = Pilot(first_name="Charles", last_name="Allen", email="cwalle@example.com")
    session.add_all([event, pilot])
    session.flush()
    prior_task = Task(
        event_id=event.id,
        name="Task 1",
        status="published",
        task_date=date(2026, 6, 1),
    )
    session.add_all([prior_task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.commit()

    task_id = resolve_active_task_id(
        session,
        pilot.id,
        now=datetime(2026, 6, 2, 14, tzinfo=UTC),
    )

    assert task_id == prior_task.id


def test_pilot_active_task_does_not_fall_back_after_comp_end_date() -> None:
    session = _session()
    event = Event(
        name="Finished Comp",
        location="Ridge",
        starts_on=date(2026, 5, 31),
        ends_on=date(2026, 6, 2),
        timezone="UTC",
    )
    pilot = Pilot(first_name="Charles", last_name="Allen", email="cwalle@example.com")
    session.add_all([event, pilot])
    session.flush()
    prior_task = Task(
        event_id=event.id,
        name="Task 1",
        status="published",
        task_date=date(2026, 6, 1),
    )
    session.add_all([prior_task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.commit()

    task_id = resolve_active_task_id(
        session,
        pilot.id,
        now=datetime(2026, 6, 3, 14, tzinfo=UTC),
    )

    assert task_id is None


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


def test_mesh_sequence_number_is_preserved_in_live_payloads() -> None:
    session = _session()
    task, _driver, pilot = _active_task_with_driver(session)
    pilot_user = User(
        username="mesh-seq-pilot@example.com",
        full_name="Mesh Sequence Pilot",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
        mesh_device_id="!seqpilot",
    )
    session.add(pilot_user)
    session.flush()

    store_position(
        session,
        task_id=task.id,
        user_id=pilot_user.id,
        pilot_id=pilot.id,
        lat=35.2,
        lon=-82.6,
        timestamp=datetime.now(UTC),
        source="mesh_relay",
        device_id="!seqpilot",
        mesh_seq_number=77,
    )
    session.commit()

    rows = get_live_positions(session, task.id)

    assert rows[0]["mesh_seq_number"] == 77
    assert rows[0]["position_source"] == "mesh"


def test_delayed_live_position_does_not_move_session_last_seen_backward() -> None:
    session = _session()
    task, _driver, pilot = _active_task_with_driver(session)
    pilot_user = User(
        username="timestamp-pilot@example.com",
        full_name="Timestamp Pilot",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    session.add(pilot_user)
    session.flush()
    now = datetime.now(UTC)

    newer = store_position(
        session,
        task_id=task.id,
        user_id=pilot_user.id,
        pilot_id=pilot.id,
        lat=35.2,
        lon=-82.6,
        timestamp=now,
        source="app",
    )
    delayed = store_position(
        session,
        task_id=task.id,
        user_id=pilot_user.id,
        pilot_id=pilot.id,
        lat=35.1,
        lon=-82.5,
        timestamp=now - timedelta(minutes=3),
        source="mesh_relay",
    )
    session.commit()

    rows = session.scalars(
        select(LivePosition)
        .where(LivePosition.pilot_id == pilot.id)
        .order_by(LivePosition.timestamp.asc())
    ).all()
    tracking = session.scalar(
        select(TrackingSession).where(
            TrackingSession.task_id == task.id,
            TrackingSession.pilot_id == pilot.id,
        )
    )

    assert [row.id for row in rows] == [delayed.id, newer.id]
    assert tracking is not None
    assert _utc(tracking.last_seen_at) == now
    assert tracking.position_count == 2


def test_live_queries_keep_current_day_offline_last_positions() -> None:
    session = _session()
    task, driver, pilot = _active_task_with_driver(session)
    now = datetime.now(UTC)
    pilot_user = User(
        username="pilot@example.com",
        full_name="Pat Pilot",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    session.add(pilot_user)
    session.flush()
    session.add_all(
        [
            TrackingSession(
                task_id=task.id,
                pilot_id=pilot.id,
                user_id=pilot_user.id,
                started_at=now - timedelta(minutes=30),
                last_seen_at=now - timedelta(minutes=10),
                is_active=True,
            ),
            TrackingSession(
                task_id=task.id,
                pilot_id=None,
                user_id=driver.id,
                started_at=now - timedelta(minutes=30),
                last_seen_at=now - timedelta(minutes=10),
                is_active=True,
            ),
            LivePosition(
                task_id=task.id,
                pilot_id=pilot.id,
                user_id=pilot_user.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(minutes=10),
                source="app",
            ),
            LivePosition(
                task_id=task.id,
                pilot_id=None,
                user_id=driver.id,
                lat=35.2,
                lon=-82.6,
                timestamp=now - timedelta(minutes=10),
                source="app",
            ),
        ]
    )
    session.commit()

    task_rows = get_live_positions(session, task.id)
    active_rows = get_all_active_positions(session, minutes=5)

    assert {row["subject_key"] for row in task_rows} == {
        f"pilot:{pilot.id}",
        f"user:{driver.id}",
    }
    assert {row["subject_key"] for row in active_rows} == {
        f"pilot:{pilot.id}",
        f"user:{driver.id}",
    }


def test_live_queries_exclude_positions_outside_current_day() -> None:
    session = _session()
    task, _driver, pilot = _active_task_with_driver(session)
    now = datetime.now(UTC)
    pilot_user = User(
        username="stale-pilot@example.com",
        full_name="Stale Pilot",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    session.add(pilot_user)
    session.flush()
    session.add_all(
        [
            TrackingSession(
                task_id=task.id,
                pilot_id=pilot.id,
                user_id=pilot_user.id,
                started_at=now - timedelta(days=1),
                last_seen_at=now - timedelta(days=1),
                is_active=True,
            ),
            LivePosition(
                task_id=task.id,
                pilot_id=pilot.id,
                user_id=pilot_user.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(days=1),
                source="app",
            ),
        ]
    )
    session.commit()

    assert get_live_positions(session, task.id) == []
    assert get_all_active_positions(session, minutes=5) == []


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


def test_driver_wifi_mesh_ingest_uses_owner_user_subject_and_car_profile() -> None:
    session = _session()
    event = Event(
        name="Tahoe Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 3),
        timezone="UTC",
    )
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    session.add_all([event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Active task", status="active", task_date=date(2026, 5, 2))
    user = User(
        username="charles@example.com",
        full_name="Charles Allen",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
    )
    session.add_all([task, user, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    session.add(
        MeshDevice(
            owner_user_id=user.id,
            device_id="!tahoe01",
            label="Tahoe",
            purpose="driver_wifi",
            is_active=True,
        )
    )
    session.commit()

    response = post_position(
        PositionPayload(
            source="mqtt_gateway",
            device_id="!tahoe01",
            lat=35.0,
            lon=-82.0,
            timestamp=datetime.now(UTC),
        ),
        user,
        session,
    )

    assert response.subject_key == f"user:{user.id}"
    assert response.pilot_id is None
    assert response.user_id == user.id
    assert response.profile_type == "driver"
    assert response.pilot_name == "Tahoe"

    rows = get_all_active_positions(session, minutes=10)
    assert len(rows) == 1
    assert rows[0]["subject_key"] == f"user:{user.id}"
    assert rows[0]["pilot_id"] is None
    assert rows[0]["profile_type"] == "driver"
    assert rows[0]["pilot_name"] == "Tahoe"


def test_pilot_phone_and_owned_mesh_positions_collapse_to_one_subject() -> None:
    session = _session()
    event = Event(
        name="Pilot Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 3),
        timezone="UTC",
    )
    pilot = Pilot(first_name="Jim", last_name="Messina", email="jim@example.com")
    session.add_all([event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Active task", status="active", task_date=date(2026, 5, 2))
    user = User(
        username="jim@example.com",
        full_name="Jim Messina",
        role="pilot",
        profile_type="pilot",
        pilot_id=pilot.id,
        mesh_device_id=None,
    )
    session.add_all([task, user, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    session.add(
        MeshDevice(
            owner_user_id=user.id,
            device_id="!0abc1234",
            label="Jim Mesh",
            purpose="tracking",
            is_active=True,
        )
    )
    session.commit()

    phone = post_position(
        PositionPayload(
            source="app",
            lat=35.0,
            lon=-82.0,
            timestamp=datetime.now(UTC) - timedelta(seconds=5),
        ),
        user,
        session,
    )
    mesh = post_position(
        PositionPayload(
            source="mesh_relay",
            device_id="!0abc1234",
            lat=35.1,
            lon=-82.1,
            timestamp=datetime.now(UTC),
        ),
        user,
        session,
    )

    assert phone.subject_key == mesh.subject_key == f"pilot:{pilot.id}"
    assert mesh.pilot_id == pilot.id
    assert mesh.user_id == user.id

    rows = get_all_active_positions(session, minutes=10)
    assert {row["subject_key"] for row in rows} == {f"pilot:{pilot.id}"}
    sessions = session.scalars(select(TrackingSession).where(TrackingSession.is_active.is_(True))).all()
    assert len(sessions) == 1
    assert sessions[0].pilot_id == pilot.id
