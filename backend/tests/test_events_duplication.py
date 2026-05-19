from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import AirspaceRegion, AirspaceSource, Event, EventPilot, IGCUpload, Pilot, ScoreResult, Task, TaskPoint, Turnpoint, TurnpointSource, User
from app.routers.events import _event_payload, duplicate_event, get_event, list_events


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


def test_event_payload_includes_public_live_tracking_flag() -> None:
    session = _session()
    event = Event(
        name="Live Public",
        location="Florida",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
        is_public_tracking=True,
    )
    session.add(event)
    session.commit()

    payload = _event_payload(session, event)

    assert payload.is_public_tracking is True


def test_list_events_filters_pilot_visible_competitions() -> None:
    session = _session()
    pilot = Pilot(first_name="Visible", last_name="Pilot", email="pilot@example.com")
    session.add(pilot)
    session.flush()
    pilot_user = User(username="visible-pilot", full_name="Visible Pilot", role="pilot", pilot_id=pilot.id, password_hash="hash")
    public_event = Event(name="Public Comp", location="Open", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC", visibility="public")
    users_event = Event(name="Users Comp", location="Portal", starts_on=date(2026, 5, 4), ends_on=date(2026, 5, 6), timezone="UTC", visibility="users")
    participant_event = Event(name="Participant Comp", location="Roster", starts_on=date(2026, 5, 7), ends_on=date(2026, 5, 9), timezone="UTC", visibility="participants")
    other_participant_event = Event(name="Other Participant Comp", location="Roster", starts_on=date(2026, 5, 10), ends_on=date(2026, 5, 12), timezone="UTC", visibility="participants")
    private_event = Event(name="Private Comp", location="Hidden", starts_on=date(2026, 5, 13), ends_on=date(2026, 5, 15), timezone="UTC", visibility="private")
    session.add_all([pilot_user, public_event, users_event, participant_event, other_participant_event, private_event])
    session.flush()
    session.add(EventPilot(event_id=participant_event.id, pilot_id=pilot.id))
    session.commit()

    visible_names = {event.name for event in list_events(user=pilot_user, session=session)}

    assert visible_names == {"Public Comp", "Users Comp", "Participant Comp"}


def test_list_events_includes_email_matched_participant_without_linked_pilot() -> None:
    session = _session()
    pilot = Pilot(first_name="Charles", last_name="Allen", email="c.allen@btcs.com")
    other_pilot = Pilot(first_name="Other", last_name="Pilot", email="other@example.com")
    user = User(username="c.allen@btcs.com", full_name="Charles Allen", role="pilot", pilot_id=None, password_hash="hash")
    participant_event = Event(name="HC 2025 - myles", location="Myles", starts_on=date(2026, 5, 7), ends_on=date(2026, 5, 9), timezone="UTC", visibility="participants")
    other_participant_event = Event(name="Other Participant Comp", location="Roster", starts_on=date(2026, 5, 10), ends_on=date(2026, 5, 12), timezone="UTC", visibility="participants")
    private_event = Event(name="Private Comp", location="Hidden", starts_on=date(2026, 5, 13), ends_on=date(2026, 5, 15), timezone="UTC", visibility="private")
    session.add_all([pilot, other_pilot, user, participant_event, other_participant_event, private_event])
    session.flush()
    session.add_all([
        EventPilot(event_id=participant_event.id, pilot_id=pilot.id),
        EventPilot(event_id=other_participant_event.id, pilot_id=other_pilot.id),
        EventPilot(event_id=private_event.id, pilot_id=pilot.id),
    ])
    session.commit()

    visible_names = {event.name for event in list_events(user=user, session=session)}

    assert "HC 2025 - myles" in visible_names
    assert "Other Participant Comp" not in visible_names
    assert "Private Comp" not in visible_names


def test_get_event_uses_same_email_participant_visibility() -> None:
    session = _session()
    pilot = Pilot(first_name="Charles", last_name="Allen", email="c.allen@btcs.com")
    user = User(username="c.allen@btcs.com", full_name="Charles Allen", role="pilot", pilot_id=None, password_hash="hash")
    unrelated = User(username="unrelated@example.com", full_name="Unrelated Pilot", role="pilot", pilot_id=None, password_hash="hash")
    participant_event = Event(name="HC 2025 - myles", location="Myles", starts_on=date(2026, 5, 7), ends_on=date(2026, 5, 9), timezone="UTC", visibility="participants")
    private_event = Event(name="Private Comp", location="Hidden", starts_on=date(2026, 5, 13), ends_on=date(2026, 5, 15), timezone="UTC", visibility="private")
    session.add_all([pilot, user, unrelated, participant_event, private_event])
    session.flush()
    session.add_all([
        EventPilot(event_id=participant_event.id, pilot_id=pilot.id),
        EventPilot(event_id=private_event.id, pilot_id=pilot.id),
    ])
    session.commit()

    assert get_event(participant_event.id, user=user, session=session).name == "HC 2025 - myles"
    with pytest.raises(HTTPException) as unrelated_error:
        get_event(participant_event.id, user=unrelated, session=session)
    assert unrelated_error.value.status_code == 404
    with pytest.raises(HTTPException) as private_error:
        get_event(private_event.id, user=user, session=session)
    assert private_error.value.status_code == 404


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
        nominal_distance_km=123,
        nominal_time_hours=4,
        nominal_launch=0.99,
        minimum_distance_km=9,
        penalties_json={"lineardist": 0.1},
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
    assert duplicated_task.nominal_distance_km != task.nominal_distance_km
    assert duplicated_task.nominal_time_hours != task.nominal_time_hours
    assert duplicated_task.nominal_launch != task.nominal_launch
    assert duplicated_task.minimum_distance_km != task.minimum_distance_km
    assert duplicated_task.penalties_json != task.penalties_json

    duplicated_task_point = session.scalar(select(TaskPoint).where(TaskPoint.task_id == duplicated_task.id))
    assert duplicated_task_point is not None
    assert duplicated_task_point.turnpoint_id == duplicated_turnpoint.id
    assert duplicated_task_point.direction == "exit"

    assert session.scalar(select(EventPilot).where(EventPilot.event_id == duplicated.id, EventPilot.pilot_id == pilot.id)) is not None
    assert session.scalar(select(IGCUpload).where(IGCUpload.event_id == duplicated.id)) is None
    assert session.scalar(select(ScoreResult).join(Task, Task.id == ScoreResult.task_id).where(Task.event_id == duplicated.id)) is None
