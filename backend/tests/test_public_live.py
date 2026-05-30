from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import BuddyGroup, BuddyGroupMember, Event, EventPilot, IGCUpload, LivePosition, Pilot, ScorePenalty, ScoreResult, Task, TrackPoint, User
from app.routers.public import (
    get_public_live_sources,
    get_public_task_results,
    get_public_upload_track,
    list_public_events,
    list_public_tasks,
    public_all_positions,
    public_buddy_group_positions,
    public_event_positions,
    public_pilot_summary,
    public_task_result_summary,
    public_task_positions,
)
from app.services.pilot_identity import merge_pilots


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_public_events_are_sorted_by_competition_date() -> None:
    session = _session()
    session.add_all(
        [
            Event(
                name="Early Open",
                location="Ridge",
                starts_on=date(2026, 4, 1),
                ends_on=date(2026, 4, 5),
                timezone="UTC",
                visibility="public",
            ),
            Event(
                name="Zulu Classic",
                location="Valley",
                starts_on=date(2026, 5, 1),
                ends_on=date(2026, 5, 3),
                timezone="UTC",
                visibility="public",
            ),
            Event(
                name="Alpine Classic",
                location="Mountain",
                starts_on=date(2026, 5, 1),
                ends_on=date(2026, 5, 3),
                timezone="UTC",
                visibility="public",
            ),
            Event(
                name="Private Future",
                location="Hidden",
                starts_on=date(2026, 6, 1),
                ends_on=date(2026, 6, 2),
                timezone="UTC",
                visibility="private",
            ),
        ]
    )
    session.commit()

    payload = list_public_events(session=session)

    assert [event.name for event in payload] == ["Alpine Classic", "Zulu Classic", "Early Open"]


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


def test_public_event_positions_exclude_unregistered_competition_pilots() -> None:
    session = _session()
    now = datetime.now(UTC)
    event = Event(
        name="Registered Only Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    registered = Pilot(first_name="Rae", last_name="Lift", email="rae@example.com")
    unregistered = Pilot(first_name="Uma", last_name="Mesh")
    session.add_all([event, registered, unregistered])
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=registered.id),
            EventPilot(event_id=event.id, pilot_id=unregistered.id),
            User(username="rae@example.com", full_name="Rae Lift", role="pilot", pilot_id=registered.id),
            LivePosition(
                pilot_id=registered.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
            LivePosition(
                pilot_id=unregistered.id,
                lat=36.0,
                lon=-83.0,
                timestamp=now - timedelta(minutes=5),
                source="mqtt_gateway",
                device_id="!unregistered",
            ),
        ]
    )
    session.commit()

    payload = public_event_positions(event.id, minutes=60, session=session)

    assert [row.pilot_id for row in payload] == [registered.id]


def test_public_all_positions_include_only_registered_users() -> None:
    session = _session()
    now = datetime.now(UTC)
    pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
    inactive_pilot = Pilot(first_name="Ivy", last_name="Idle", email="ivy@example.com")
    session.add_all([pilot, inactive_pilot])
    session.flush()
    pilot_user = User(username="ari@example.com", full_name="Ari Sky", role="pilot", pilot_id=pilot.id)
    driver = User(username="driver@example.com", full_name="Dee Driver", role="driver", profile_type="driver")
    inactive_user = User(
        username="ivy@example.com",
        full_name="Ivy Idle",
        role="pilot",
        pilot_id=inactive_pilot.id,
        is_active=False,
    )
    node = User(
        username="node@example.com",
        full_name="Relay Node",
        role="pilot",
        profile_type="stationary_node",
    )
    session.add_all([pilot_user, driver, inactive_user, node])
    session.flush()
    session.add_all(
        [
            LivePosition(
                pilot_id=pilot.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
            LivePosition(
                user_id=driver.id,
                lat=35.1,
                lon=-82.1,
                timestamp=now - timedelta(minutes=4),
                source="app",
            ),
            LivePosition(
                pilot_id=inactive_pilot.id,
                user_id=inactive_user.id,
                lat=35.2,
                lon=-82.2,
                timestamp=now - timedelta(minutes=3),
                source="app",
            ),
            LivePosition(
                user_id=node.id,
                lat=35.3,
                lon=-82.3,
                timestamp=now - timedelta(minutes=2),
                source="mqtt_gateway",
            ),
            LivePosition(
                lat=35.4,
                lon=-82.4,
                timestamp=now - timedelta(minutes=1),
                source="mqtt_gateway",
                device_id="!randommesh",
            ),
        ]
    )
    session.commit()

    payload = public_all_positions(minutes=60, limit=100, session=session)

    assert {row.subject_key for row in payload} == {f"pilot:{pilot.id}", f"user:{driver.id}"}


def test_public_buddy_group_positions_include_only_registered_group_members() -> None:
    session = _session()
    now = datetime.now(UTC)
    owner = User(username="owner@example.com", full_name="Owner", role="organizer")
    member = Pilot(first_name="Mia", last_name="Member", email="mia@example.com")
    unregistered_member = Pilot(first_name="Una", last_name="Unregistered")
    outsider = Pilot(first_name="Oli", last_name="Outside", email="oli@example.com")
    session.add_all([owner, member, unregistered_member, outsider])
    session.flush()
    group = BuddyGroup(user_id=owner.id, name="Public Crew", is_public=True)
    session.add(group)
    session.flush()
    session.add_all(
        [
            BuddyGroupMember(group_id=group.id, pilot_id=member.id),
            BuddyGroupMember(group_id=group.id, pilot_id=unregistered_member.id),
            User(username="mia@example.com", full_name="Mia Member", role="pilot", pilot_id=member.id),
            User(username="oli@example.com", full_name="Oli Outside", role="pilot", pilot_id=outsider.id),
            LivePosition(
                pilot_id=member.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
            LivePosition(
                pilot_id=unregistered_member.id,
                lat=35.1,
                lon=-82.1,
                timestamp=now - timedelta(minutes=4),
                source="mqtt_gateway",
                device_id="!groupdevice",
            ),
            LivePosition(
                pilot_id=outsider.id,
                lat=35.2,
                lon=-82.2,
                timestamp=now - timedelta(minutes=3),
                source="app",
            ),
        ]
    )
    session.commit()

    payload = public_buddy_group_positions(group.id, minutes=60, limit=100, session=session)

    assert [row.pilot_id for row in payload] == [member.id]


def test_public_task_positions_include_only_registered_event_members() -> None:
    session = _session()
    now = datetime.now(UTC)
    event = Event(
        name="Task Live Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        is_public_tracking=True,
    )
    registered = Pilot(first_name="Tia", last_name="Task", email="tia@example.com")
    unregistered = Pilot(first_name="Una", last_name="Task")
    outsider = Pilot(first_name="Oli", last_name="Outside", email="oli-task@example.com")
    session.add_all([event, registered, unregistered, outsider])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="active", task_date=date(2026, 5, 2))
    session.add(task)
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=registered.id),
            EventPilot(event_id=event.id, pilot_id=unregistered.id),
            User(username="tia@example.com", full_name="Tia Task", role="pilot", pilot_id=registered.id),
            User(username="oli-task@example.com", full_name="Oli Outside", role="pilot", pilot_id=outsider.id),
            LivePosition(
                task_id=task.id,
                pilot_id=registered.id,
                lat=35.0,
                lon=-82.0,
                timestamp=now - timedelta(minutes=5),
                source="app",
            ),
            LivePosition(
                task_id=task.id,
                pilot_id=unregistered.id,
                lat=35.1,
                lon=-82.1,
                timestamp=now - timedelta(minutes=4),
                source="mqtt_gateway",
                device_id="!taskdevice",
            ),
            LivePosition(
                task_id=task.id,
                pilot_id=outsider.id,
                lat=35.2,
                lon=-82.2,
                timestamp=now - timedelta(minutes=3),
                source="app",
            ),
        ]
    )
    session.commit()

    payload = public_task_positions(task.id, session=session)

    assert [row.pilot_id for row in payload] == [registered.id]


def test_public_event_positions_include_live_rows_after_duplicate_pilot_merge() -> None:
    session = _session()
    now = datetime.now(UTC)
    event = Event(
        name="HC 2026",
        location="Myles",
        starts_on=date(2026, 5, 29),
        ends_on=date(2026, 6, 6),
        timezone="UTC",
        is_public_tracking=True,
    )
    roster_pilot = Pilot(first_name="Mick", last_name="Howard")
    duplicate_pilot = Pilot(first_name="Mick", last_name="Howard", email="mick@example.com")
    session.add_all([event, roster_pilot, duplicate_pilot])
    session.flush()
    user = User(username="mick@example.com", full_name="Mick Howard", role="pilot", pilot_id=duplicate_pilot.id)
    session.add(user)
    session.flush()
    session.add_all(
        [
            EventPilot(event_id=event.id, pilot_id=roster_pilot.id),
            LivePosition(
                pilot_id=duplicate_pilot.id,
                user_id=user.id,
                lat=40.0,
                lon=-75.0,
                timestamp=now - timedelta(minutes=1),
                source="mqtt_gateway",
            ),
        ]
    )
    session.commit()

    assert public_event_positions(event.id, minutes=60, session=session) == []

    merge_pilots(session, source_pilot_id=duplicate_pilot.id, target_pilot_id=roster_pilot.id)
    session.commit()

    payload = public_event_positions(event.id, minutes=60, session=session)

    assert len(payload) == 1
    row = payload[0].model_dump()
    assert row["pilot_id"] == roster_pilot.id
    assert row["pilot_name"] == "Mick Howard"


def _score(
    task: Task,
    pilot: Pilot,
    *,
    rank: int,
    points: float,
    state: str = "official",
    status: str = "goal",
    quality: float | None = None,
    upload_id: int | None = None,
) -> ScoreResult:
    details_json = {}
    if quality is not None:
        details_json = {"gap": {"validity": {"overall": quality}}}
    return ScoreResult(
        task_id=task.id,
        pilot_id=pilot.id,
        upload_id=upload_id,
        status=status,
        rank=rank,
        distance_flown_km=42,
        raw_score_points=points,
        score_points=points,
        details_json=details_json,
        result_state=state,
    )


def test_public_tasks_include_only_published_tasks_for_public_events() -> None:
    session = _session()
    public_event = Event(
        name="Public Scores Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    private_event = Event(
        name="Private Scores Comp",
        location="Valley",
        starts_on=date(2026, 5, 8),
        ends_on=date(2026, 5, 9),
        timezone="UTC",
        visibility="private",
    )
    session.add_all([public_event, private_event])
    session.flush()
    session.add_all(
        [
            Task(event_id=public_event.id, name="Newer Published", status="published", task_date=date(2026, 5, 5)),
            Task(event_id=public_event.id, name="Practice Published", status="published", task_date=date(2026, 5, 4), is_practice=True),
            Task(event_id=public_event.id, name="Undated Published", status="published", task_date=None),
            Task(event_id=public_event.id, name="Older Published", status="published", task_date=date(2026, 5, 2)),
            Task(event_id=public_event.id, name="Draft", status="draft", task_date=date(2026, 5, 3)),
            Task(event_id=private_event.id, name="Private Published", status="published", task_date=date(2026, 5, 4)),
        ]
    )
    session.commit()

    payload = list_public_tasks(public_event.id, session=session)

    assert [task.name for task in payload] == ["Practice Published", "Older Published", "Newer Published", "Undated Published"]
    with pytest.raises(HTTPException) as caught:
        list_public_tasks(private_event.id, session=session)
    assert caught.value.status_code == 404


def test_public_task_results_include_provisional_scores() -> None:
    session = _session()
    event = Event(
        name="Public Result Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    official_pilot = Pilot(first_name="Ada", last_name="Cloud")
    provisional_pilot = Pilot(first_name="Ben", last_name="Thermal")
    unscored_pilot = Pilot(first_name="Cara", last_name="Waiting")
    session.add_all([event, official_pilot, provisional_pilot, unscored_pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add_all(
        [
            task,
            EventPilot(event_id=event.id, pilot_id=official_pilot.id),
            EventPilot(event_id=event.id, pilot_id=provisional_pilot.id),
            EventPilot(event_id=event.id, pilot_id=unscored_pilot.id),
        ]
    )
    session.flush()
    session.add_all(
        [
            _score(task, official_pilot, rank=1, points=901, state="official"),
            _score(task, provisional_pilot, rank=2, points=875, state="provisional"),
        ]
    )
    session.commit()

    payload = get_public_task_results(task.id, session=session)

    assert [result.pilot_name for result in payload] == ["Ada Cloud", "Ben Thermal", "Cara Waiting"]
    assert payload[0].result_state == "official"
    assert payload[1].result_state == "provisional"
    assert payload[2].result_state == "unscored"
    assert payload[2].rank is None
    assert payload[2].score_points == 0


def test_public_task_results_include_public_safe_penalty_details() -> None:
    session = _session()
    event = Event(
        name="Public Penalty Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    pilot = Pilot(first_name="Ada", last_name="Cloud")
    session.add_all([event, pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add_all([task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    details_json = {
        "start_timing": {
            "actual_start_crossing_at": "2026-05-02T14:14:45Z",
            "start_gate_index": 1,
            "start_gate_time": "2026-05-02T14:15:00Z",
            "jump_the_gun_seconds": 15,
            "jump_the_gun_penalty_seconds": 15,
            "jump_the_gun_penalty_points": 30,
        },
        "gap": {"formula": {"jump_the_gun_factor": 2}},
    }
    session.add(
        ScoreResult(
            task_id=task.id,
            pilot_id=pilot.id,
            status="goal",
            rank=1,
            distance_flown_km=42,
            raw_score_points=900,
            score_points=855,
            details_json=details_json,
            result_state="official",
        )
    )
    session.add(ScorePenalty(task_id=task.id, pilot_id=pilot.id, penalty_type="fixed", value=45, reason="Airspace", position=0))
    session.commit()

    payload = get_public_task_results(task.id, session=session)

    assert len(payload) == 1
    assert payload[0].penalty_summary == "Early start penalty -30 pts, -45 pts"
    assert payload[0].penalties[0].reason == "Airspace"
    assert payload[0].penalties[0].applied_by is None
    assert payload[0].penalty_calculation is not None
    assert payload[0].penalty_calculation.engine_penalty_points == 30
    assert payload[0].penalty_calculation.manual_penalty_points == 45
    assert payload[0].penalty_calculation.total_display_penalty_points == 75


def test_public_pilot_summary_uses_only_official_scores() -> None:
    session = _session()
    event = Event(
        name="Public Overall Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    pilot = Pilot(first_name="Casey", last_name="Lift")
    session.add_all([event, pilot])
    session.flush()
    official_task = Task(event_id=event.id, name="Official Task", status="published", task_date=date(2026, 5, 2))
    provisional_task = Task(event_id=event.id, name="Provisional Task", status="published", task_date=date(2026, 5, 3))
    practice_task = Task(event_id=event.id, name="Practice Task", status="published", task_date=date(2026, 5, 1), is_practice=True)
    session.add_all([official_task, provisional_task, practice_task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    session.add_all(
        [
            _score(official_task, pilot, rank=1, points=910, state="official"),
            _score(provisional_task, pilot, rank=1, points=870, state="provisional"),
            _score(practice_task, pilot, rank=1, points=800, state="official"),
        ]
    )
    session.commit()

    payload = public_pilot_summary(event.id, session=session)

    assert len(payload) == 1
    assert payload[0].total_score_points == 1780
    assert payload[0].tasks_scored == 2
    assert payload[0].task_scores == {practice_task.id: 800, official_task.id: 910, provisional_task.id: 870}
    assert payload[0].task_result_states == {
        practice_task.id: "official",
        official_task.id: "official",
        provisional_task.id: "provisional",
    }
    assert payload[0].task_statuses == {
        practice_task.id: "goal",
        official_task.id: "goal",
        provisional_task.id: "goal",
    }


def test_public_pilot_summary_includes_absent_and_dnf_task_statuses() -> None:
    session = _session()
    event = Event(
        name="Public Status Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    absent_pilot = Pilot(first_name="Ada", last_name="Absent")
    dnf_pilot = Pilot(first_name="Ben", last_name="Grounded")
    session.add_all([event, absent_pilot, dnf_pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add_all([
        task,
        EventPilot(event_id=event.id, pilot_id=absent_pilot.id),
        EventPilot(event_id=event.id, pilot_id=dnf_pilot.id),
    ])
    session.flush()
    session.add_all([
        _score(task, absent_pilot, rank=1, points=0, status="absent"),
        _score(task, dnf_pilot, rank=2, points=0, status="did_not_fly"),
    ])
    session.commit()

    payload = public_pilot_summary(event.id, session=session)
    summaries_by_name = {summary.pilot_name: summary for summary in payload}

    assert summaries_by_name["Ada Absent"].task_scores == {task.id: 0}
    assert summaries_by_name["Ada Absent"].task_statuses == {task.id: "absent"}
    assert summaries_by_name["Ben Grounded"].task_scores == {task.id: 0}
    assert summaries_by_name["Ben Grounded"].task_statuses == {task.id: "did_not_fly"}


def test_public_task_result_summary_includes_provisional_scores() -> None:
    session = _session()
    event = Event(
        name="Public Day Quality Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    pilot = Pilot(first_name="Dee", last_name="Glide")
    session.add_all([event, pilot])
    session.flush()
    official_task = Task(event_id=event.id, name="Official Task", status="published", task_date=date(2026, 5, 2))
    provisional_task = Task(event_id=event.id, name="Provisional Task", status="published", task_date=date(2026, 5, 3))
    draft_task = Task(event_id=event.id, name="Draft Task", status="draft", task_date=date(2026, 5, 4))
    session.add_all([official_task, provisional_task, draft_task])
    session.flush()
    session.add_all(
        [
            _score(official_task, pilot, rank=1, points=920, state="official", quality=0.91),
            _score(provisional_task, pilot, rank=1, points=880, state="provisional", quality=0.72),
            _score(draft_task, pilot, rank=1, points=840, state="official", quality=0.66),
        ]
    )
    session.commit()

    payload = public_task_result_summary(event.id, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in payload] == [(official_task.id, 0.91), (provisional_task.id, 0.72)]


def test_public_upload_track_is_available_for_public_official_results() -> None:
    session = _session()
    event = Event(
        name="Public Track Comp",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    pilot = Pilot(first_name="Eli", last_name="Cloud")
    user = User(username="eli@example.com", full_name="Eli Cloud", role="pilot", pilot_id=None, aircraft_icon="paraglider")
    session.add_all([event, pilot, user])
    session.flush()
    user.pilot_id = pilot.id
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add(task)
    session.flush()
    upload = IGCUpload(
        event_id=event.id,
        task_id=task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=user.id,
        filename="eli.igc",
        sha256="e" * 64,
        stored_path="/tmp/eli.igc",
        metadata_json={},
    )
    session.add(upload)
    session.flush()
    session.add_all(
        [
            TrackPoint(
                upload_id=upload.id,
                sequence=1,
                recorded_at=datetime(2026, 5, 2, 12, 0, tzinfo=UTC),
                latitude=35.0,
                longitude=-82.0,
                pressure_altitude_m=1000,
                gps_altitude_m=1010,
            ),
            TrackPoint(
                upload_id=upload.id,
                sequence=2,
                recorded_at=datetime(2026, 5, 2, 12, 5, tzinfo=UTC),
                latitude=35.1,
                longitude=-82.1,
                pressure_altitude_m=1100,
                gps_altitude_m=1110,
            ),
            _score(task, pilot, rank=1, points=900, state="official", upload_id=upload.id),
        ]
    )
    session.commit()

    payload = get_public_upload_track(upload.id, session=session)

    feature = payload["features"][0]
    assert feature["properties"]["upload_id"] == upload.id
    assert feature["properties"]["pilot_name"] == "Eli Cloud"
    assert feature["properties"]["aircraft_icon"] == "paraglider"
    assert feature["properties"]["timestamps"] == ["2026-05-02T12:00:00Z", "2026-05-02T12:05:00Z"]
    assert feature["geometry"]["coordinates"] == [[-82.0, 35.0, 1010.0], [-82.1, 35.1, 1110.0]]


def test_public_upload_track_requires_public_official_result() -> None:
    session = _session()
    public_event = Event(
        name="Public Track Locks",
        location="Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
        visibility="public",
    )
    private_event = Event(
        name="Private Track Locks",
        location="Valley",
        starts_on=date(2026, 5, 8),
        ends_on=date(2026, 5, 9),
        timezone="UTC",
        visibility="private",
    )
    pilot = Pilot(first_name="Finn", last_name="Lift")
    other_pilot = Pilot(first_name="Gia", last_name="Thermal")
    user = User(username="uploader@example.com", full_name="Uploader", role="organizer")
    session.add_all([public_event, private_event, pilot, other_pilot, user])
    session.flush()
    public_task = Task(event_id=public_event.id, name="Public Task", status="published", task_date=date(2026, 5, 2))
    private_task = Task(event_id=private_event.id, name="Private Task", status="published", task_date=date(2026, 5, 8))
    session.add_all([public_task, private_task])
    session.flush()
    provisional_upload = IGCUpload(
        event_id=public_event.id,
        task_id=public_task.id,
        pilot_id=pilot.id,
        uploaded_by_user_id=user.id,
        filename="provisional.igc",
        sha256="p" * 64,
        stored_path="/tmp/provisional.igc",
        metadata_json={},
    )
    private_upload = IGCUpload(
        event_id=private_event.id,
        task_id=private_task.id,
        pilot_id=other_pilot.id,
        uploaded_by_user_id=user.id,
        filename="private.igc",
        sha256="f" * 64,
        stored_path="/tmp/private.igc",
        metadata_json={},
    )
    session.add_all([provisional_upload, private_upload])
    session.flush()
    session.add_all(
        [
            _score(public_task, pilot, rank=1, points=800, state="provisional", upload_id=provisional_upload.id),
            _score(private_task, other_pilot, rank=1, points=900, state="official", upload_id=private_upload.id),
        ]
    )
    session.commit()

    for upload_id in (provisional_upload.id, private_upload.id):
        with pytest.raises(HTTPException) as caught:
            get_public_upload_track(upload_id, session=session)
        assert caught.value.status_code == 404
