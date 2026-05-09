from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import BuddyGroup, BuddyGroupMember, Event, EventPilot, LivePosition, Pilot, Task, User
from app.routers.public import get_public_live_sources, public_event_positions


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_public_live_sources_lists_competitions_and_public_groups() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="organizer")
    pilot = Pilot(first_name="Casey", last_name="Cloud", email="casey@example.com")
    live_event = Event(
        name="Open Distance Classic",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    hidden_event = Event(
        name="Private Practice",
        location="Valley",
        starts_on=date(2026, 5, 8),
        ends_on=date(2026, 5, 9),
        timezone="UTC",
        is_public_tracking=False,
    )
    session.add_all([owner, pilot, live_event, hidden_event])
    session.flush()
    session.add_all(
        [
            Task(event_id=live_event.id, name="Published task", status="published", task_date=date(2026, 5, 2)),
            Task(event_id=live_event.id, name="Active task", status="active", task_date=date(2026, 5, 3)),
            Task(event_id=live_event.id, name="Draft task", status="draft", task_date=date(2026, 5, 4)),
            BuddyGroup(user_id=owner.id, name="Public crew", is_public=True),
            BuddyGroup(user_id=owner.id, name="Private crew", is_public=False),
        ]
    )
    session.flush()
    public_group = session.query(BuddyGroup).filter(BuddyGroup.name == "Public crew").one()
    session.add(BuddyGroupMember(group_id=public_group.id, pilot_id=pilot.id))
    session.commit()

    payload = get_public_live_sources(session)

    assert [event.name for event in payload.events] == ["Open Distance Classic"]
    assert [task.name for task in payload.events[0].tasks] == ["Published task", "Active task"]
    assert payload.events[0].map_task is not None
    assert payload.events[0].map_task.name == "Active task"
    assert [(group.name, group.member_count) for group in payload.buddy_groups] == [("Public crew", 1)]


def test_public_live_map_task_falls_back_to_newest_published_task() -> None:
    session = _session()
    event = Event(
        name="Fallback Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    session.add(event)
    session.flush()
    session.add_all(
        [
            Task(event_id=event.id, name="Older published", status="published", task_date=date(2026, 5, 2)),
            Task(event_id=event.id, name="Newest published", status="published", task_date=date(2026, 5, 5)),
            Task(event_id=event.id, name="Newest draft", status="draft", task_date=date(2026, 5, 6)),
        ]
    )
    session.commit()

    payload = get_public_live_sources(session)

    assert payload.events[0].map_task is not None
    assert payload.events[0].map_task.name == "Newest published"


def test_public_live_map_task_is_empty_without_active_or_published_tasks() -> None:
    session = _session()
    event = Event(
        name="Draft Only Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    session.add(event)
    session.flush()
    session.add(Task(event_id=event.id, name="Draft task", status="draft", task_date=date(2026, 5, 6)))
    session.commit()

    payload = get_public_live_sources(session)

    assert payload.events[0].tasks == []
    assert payload.events[0].map_task is None


def test_public_event_positions_are_limited_to_competition_pilots() -> None:
    session = _session()
    now = datetime.now(UTC)
    event = Event(
        name="Live Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
    outsider = Pilot(first_name="Noa", last_name="Away", email="noa@example.com")
    session.add_all([event, pilot, outsider])
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=pilot.id),
            User(username="ari@example.com", full_name="Ari Sky", role="pilot", pilot_id=pilot.id),
            User(username="noa@example.com", full_name="Noa Away", role="pilot", pilot_id=outsider.id),
            LivePosition(
                pilot_id=pilot.id,
                lat=35.0,
                lon=-82.0,
                alt=1200,
                speed=42,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
            LivePosition(
                pilot_id=pilot.id,
                lat=34.0,
                lon=-81.0,
                timestamp=now - timedelta(days=2),
                source="app",
            ),
            LivePosition(
                pilot_id=outsider.id,
                lat=36.0,
                lon=-83.0,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
        ]
    )
    session.commit()

    payload = public_event_positions(event.id, minutes=60, limit=100, session=session)

    assert len(payload) == 1
    row = payload[0].model_dump()
    assert row["pilot_id"] == pilot.id
    assert row["pilot_name"] == "Ari Sky"
    assert row["position_source"] == "cellular"
