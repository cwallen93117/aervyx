from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import BuddyGroup, BuddyGroupMember, Event, EventPilot, IGCUpload, LivePosition, Pilot, ScoreResult, Task, TrackPoint, User
from app.routers.public import (
    get_public_live_sources,
    get_public_task_results,
    get_public_upload_track,
    list_public_events,
    list_public_tasks,
    public_event_positions,
    public_pilot_summary,
    public_task_result_summary,
)


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


def _score(
    task: Task,
    pilot: Pilot,
    *,
    rank: int,
    points: float,
    state: str = "official",
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
        status="goal",
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
            Task(event_id=public_event.id, name="Undated Published", status="published", task_date=None),
            Task(event_id=public_event.id, name="Older Published", status="published", task_date=date(2026, 5, 2)),
            Task(event_id=public_event.id, name="Draft", status="draft", task_date=date(2026, 5, 3)),
            Task(event_id=private_event.id, name="Private Published", status="published", task_date=date(2026, 5, 4)),
        ]
    )
    session.commit()

    payload = list_public_tasks(public_event.id, session=session)

    assert [task.name for task in payload] == ["Older Published", "Newer Published", "Undated Published"]
    with pytest.raises(HTTPException) as caught:
        list_public_tasks(private_event.id, session=session)
    assert caught.value.status_code == 404


def test_public_task_results_hide_provisional_scores() -> None:
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
    session.add_all([event, official_pilot, provisional_pilot])
    session.flush()
    task = Task(event_id=event.id, name="Task 1", status="published", task_date=date(2026, 5, 2))
    session.add(task)
    session.flush()
    session.add_all(
        [
            _score(task, official_pilot, rank=1, points=901, state="official"),
            _score(task, provisional_pilot, rank=2, points=875, state="provisional"),
        ]
    )
    session.commit()

    payload = get_public_task_results(task.id, session=session)

    assert [result.pilot_name for result in payload] == ["Ada Cloud"]
    assert payload[0].result_state == "official"


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
    session.add_all([official_task, provisional_task, EventPilot(event_id=event.id, pilot_id=pilot.id)])
    session.flush()
    session.add_all(
        [
            _score(official_task, pilot, rank=1, points=910, state="official"),
            _score(provisional_task, pilot, rank=1, points=870, state="provisional"),
        ]
    )
    session.commit()

    payload = public_pilot_summary(event.id, session=session)

    assert len(payload) == 1
    assert payload[0].total_score_points == 910
    assert payload[0].tasks_scored == 1
    assert payload[0].task_scores == {official_task.id: 910}
    assert payload[0].task_result_states == {official_task.id: "official"}


def test_public_task_result_summary_uses_only_official_scores() -> None:
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

    assert [(summary.task_id, summary.day_quality) for summary in payload] == [(official_task.id, 0.91)]


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
