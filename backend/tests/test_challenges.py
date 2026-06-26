from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import AirspaceRegion, AirspaceSource, BuddyGroup, BuddyGroupMember, Event, EventPilot, Pilot, Task, TaskPoint, Turnpoint, TurnpointSource, User
from app.routers.challenges import create_challenge, get_challenge
from app.routers.events import create_event
from app.routers.public import get_public_challenge_by_slug, list_public_events
from app.routers.tasks import publish_task
from app.schemas import ChallengeCreate, EventCreate


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_pilot_creates_unlisted_public_challenge_from_buddy_group_defaults() -> None:
    session = _session()
    owner_pilot = Pilot(first_name="Owner", last_name="Pilot", email="owner@example.com")
    buddy_pilot = Pilot(first_name="Buddy", last_name="Pilot", email="buddy@example.com")
    outsider = Pilot(first_name="Outside", last_name="Pilot", email="outside@example.com")
    session.add_all([owner_pilot, buddy_pilot, outsider])
    session.flush()
    owner = User(
        username="owner@example.com",
        full_name="Owner Pilot",
        role="pilot",
        pilot_id=owner_pilot.id,
        password_hash="hash",
        challenge_settings_json={"minimum_distance_km": 9, "default_start_gate_count": 3},
    )
    session.add(owner)
    session.flush()
    group = BuddyGroup(user_id=owner.id, name="Weekend crew")
    session.add(group)
    session.flush()
    session.add(BuddyGroupMember(group_id=group.id, pilot_id=buddy_pilot.id))
    session.commit()

    payload = create_challenge(
        ChallengeCreate(
            name="Sunday XC",
            challenge_type="open_distance",
            starts_on=date(2026, 6, 21),
            ends_on=date(2026, 6, 21),
            source_buddy_group_id=group.id,
        ),
        user=owner,
        session=session,
    )

    event = session.get(Event, payload.id)
    assert event is not None
    assert event.event_kind == "challenge"
    assert event.owner_user_id == owner.id
    assert event.source_buddy_group_id == group.id
    assert event.visibility == "public"
    assert event.public_listed is False
    assert event.minimum_distance_km == 9
    assert event.default_start_gate_count == 3
    assert payload.public_url == f"/scores?challenge={event.public_slug}"
    roster = set(session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event.id)).all())
    assert roster == {owner_pilot.id, buddy_pilot.id}
    task = session.scalar(select(Task).where(Task.event_id == event.id))
    assert task is not None
    assert task.task_type == "open_distance"

    assert [event.name for event in list_public_events(session=session)] == []
    assert get_public_challenge_by_slug(event.public_slug, session=session).id == event.id
    assert outsider.id not in roster


def test_pilot_creates_buddy_challenge_through_event_api() -> None:
    session = _session()
    owner_pilot = Pilot(first_name="Owner", last_name="Pilot", email="owner@example.com")
    buddy_pilot = Pilot(first_name="Buddy", last_name="Pilot", email="buddy@example.com")
    session.add_all([owner_pilot, buddy_pilot])
    session.flush()
    owner = User(
        username="owner@example.com",
        full_name="Owner Pilot",
        role="pilot",
        pilot_id=owner_pilot.id,
        password_hash="hash",
        challenge_settings_json={"minimum_distance_km": 13, "default_start_gate_count": 2},
    )
    session.add(owner)
    session.flush()
    group = BuddyGroup(user_id=owner.id, name="Weekend crew")
    session.add(group)
    session.flush()
    session.add(BuddyGroupMember(group_id=group.id, pilot_id=buddy_pilot.id))
    session.commit()

    payload = create_event(
        EventCreate(
            name="Weekend XC",
            location="Home ridge",
            starts_on=date(2026, 6, 21),
            ends_on=date(2026, 6, 21),
            timezone="UTC",
            event_kind="challenge",
            source_buddy_group_id=group.id,
            visibility="public",
            public_listed=True,
            minimum_distance_km=11,
            default_start_gate_count=4,
        ),
        user=owner,
        session=session,
    )

    event = session.get(Event, payload.id)
    assert event is not None
    assert event.event_kind == "challenge"
    assert event.owner_user_id == owner.id
    assert event.source_buddy_group_id == group.id
    assert event.public_slug
    assert event.public_listed is True
    assert event.minimum_distance_km == 13
    assert event.default_start_gate_count == 2
    roster = set(session.scalars(select(EventPilot.pilot_id).where(EventPilot.event_id == event.id)).all())
    assert roster == {owner_pilot.id, buddy_pilot.id}
    task = session.scalar(select(Task).where(Task.event_id == event.id))
    assert task is not None
    assert task.task_type == "open_distance"


def test_challenge_creation_copies_default_sources_and_task_points_can_use_them() -> None:
    session = _session()
    owner_pilot = Pilot(first_name="Owner", last_name="Pilot", email="owner@example.com")
    session.add(owner_pilot)
    session.flush()
    owner = User(username="owner@example.com", full_name="Owner Pilot", role="pilot", pilot_id=owner_pilot.id, password_hash="hash")
    session.add(owner)
    session.flush()
    template = Event(
        name="Challenge Defaults",
        location="",
        starts_on=date(2026, 6, 20),
        ends_on=date(2026, 6, 20),
        timezone="UTC",
        event_kind="challenge_defaults",
        owner_user_id=owner.id,
        visibility="private",
        public_listed=False,
    )
    session.add(template)
    session.flush()
    turnpoint_source = TurnpointSource(
        event_id=template.id,
        filename="default.csv",
        content_type="text/csv",
        file_format="csv",
        sha256="tp",
        stored_path="missing-default.csv",
        enabled=True,
    )
    airspace_source = AirspaceSource(
        event_id=template.id,
        kind="airspace",
        filename="airspace.txt",
        content_type="text/plain",
        file_format="openair",
        sha256="air",
        stored_path="missing-airspace.txt",
        enabled=True,
    )
    session.add_all([turnpoint_source, airspace_source])
    session.flush()
    session.add(Turnpoint(event_id=template.id, source_id=turnpoint_source.id, name="START", latitude=39.0, longitude=-105.0, source_row_index=0))
    session.add(
        AirspaceRegion(
            event_id=template.id,
            source_id=airspace_source.id,
            name="Test Airspace",
            display_category="B",
            geometry_json={"type": "Polygon", "coordinates": []},
            is_restricted_field=False,
        )
    )
    owner.challenge_settings_json = {
        "template_event_id": template.id,
        "turnpoint_source_id": turnpoint_source.id,
        "airspace_source_id": airspace_source.id,
        "minimum_distance_km": 12,
    }
    session.commit()

    payload = create_challenge(
        ChallengeCreate(
            name="Copied defaults",
            starts_on=date(2026, 6, 21),
            ends_on=date(2026, 6, 21),
        ),
        user=owner,
        session=session,
    )

    event = session.get(Event, payload.id)
    assert event is not None
    assert event.minimum_distance_km == 12
    copied_turnpoint = session.scalar(select(Turnpoint).where(Turnpoint.event_id == event.id))
    assert copied_turnpoint is not None
    assert copied_turnpoint.name == "START"
    copied_airspace = session.scalar(select(AirspaceRegion).where(AirspaceRegion.event_id == event.id))
    assert copied_airspace is not None
    assert copied_airspace.name == "Test Airspace"
    task = session.scalar(select(Task).where(Task.event_id == event.id))
    assert task is not None
    session.add(TaskPoint(task_id=task.id, position=1, point_type="start", turnpoint_id=copied_turnpoint.id, name=copied_turnpoint.name, latitude=copied_turnpoint.latitude, longitude=copied_turnpoint.longitude))
    session.commit()
    assert session.scalar(select(TaskPoint).where(TaskPoint.task_id == task.id)).turnpoint_id == copied_turnpoint.id


def test_non_owner_cannot_manage_challenge_task() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.flush()
    event = Event(
        name="Private Challenge",
        location="",
        starts_on=date(2026, 6, 21),
        ends_on=date(2026, 6, 21),
        timezone="UTC",
        event_kind="challenge",
        owner_user_id=owner.id,
    )
    session.add(event)
    session.flush()
    task = Task(event_id=event.id, name="Task", status="draft", task_type="open_distance")
    session.add(task)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        publish_task(task.id, admin=other, session=session)

    assert exc.value.status_code == 403
    assert publish_task(task.id, admin=owner, session=session).status == "published"


def test_private_challenge_slug_is_not_public() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", password_hash="hash")
    session.add(owner)
    session.flush()
    event = Event(
        name="Hidden Challenge",
        location="",
        starts_on=date(2026, 6, 21),
        ends_on=date(2026, 6, 21),
        timezone="UTC",
        event_kind="challenge",
        owner_user_id=owner.id,
        public_slug="hidden-123",
        visibility="private",
        public_listed=False,
    )
    session.add(event)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        get_public_challenge_by_slug("hidden-123", session=session)

    assert exc.value.status_code == 404
    assert get_challenge(event.id, user=owner, session=session).id == event.id
