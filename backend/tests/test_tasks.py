from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, Task, TaskPoint, Turnpoint, TurnpointSource, User
from app.routers.tasks import _task_response, create_task, delete_task, list_tasks, unpublish_task, update_task
from app.schemas import TaskInput


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_task_response_filters_stale_turnpoints_when_sources_are_disabled() -> None:
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
        enabled=True,
    )
    stale_source = TurnpointSource(
        event_id=event.id,
        filename="west.gpx",
        content_type="application/gpx+xml",
        file_format="gpx",
        sha256="b" * 64,
        stored_path="/tmp/west.gpx",
        enabled=False,
    )
    session.add_all([active_source, stale_source])
    session.flush()

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
    assert response.task_type == "race_to_goal_with_gates"
    assert response.is_practice is False
    assert response.start_gate_count == 1
    assert [point.direction for point in response.points] == ["enter", "enter"]
    assert not hasattr(response, "nominal_distance_km")
    assert not hasattr(response, "minimum_distance_km")


def test_task_input_ignores_deprecated_formula_fields() -> None:
    payload = TaskInput(
        name="Task 1",
        nominal_distance_km=123,
        nominal_time_hours=4,
        nominal_launch=0.99,
        minimum_distance_km=9,
        penalties_json={"lineardist": 0.1},
        points=[
            {
                "position": 1,
                "point_type": "goal",
                "radius_m": 400,
                "name": "Goal",
                "latitude": 38.0,
                "longitude": -75.0,
            }
        ],
    )

    assert not hasattr(payload, "nominal_distance_km")
    assert not hasattr(payload, "nominal_time_hours")
    assert not hasattr(payload, "nominal_launch")
    assert not hasattr(payload, "minimum_distance_km")
    assert not hasattr(payload, "penalties_json")


def test_create_task_defaults_point_radius_and_direction_by_type() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    event = Event(
        name="Default Task Points",
        location="Ridgeline",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
    )
    session.add_all([admin, event])
    session.flush()

    payload = TaskInput(
        name="Practice",
        is_practice=True,
        points=[
            {
                "position": 1,
                "point_type": "start",
                "name": "Start",
                "latitude": 38.0,
                "longitude": -75.0,
            },
            {
                "position": 2,
                "point_type": "turnpoint",
                "name": "Turn",
                "latitude": 38.1,
                "longitude": -75.1,
            },
            {
                "position": 3,
                "point_type": "goal",
                "radius_m": 0,
                "name": "Goal",
                "latitude": 38.2,
                "longitude": -75.2,
            },
        ],
    )

    response = create_task(event.id, payload, admin=admin, session=session)

    assert response.is_practice is True
    assert [(point.point_type, point.direction, point.radius_m) for point in response.points] == [
        ("start", "exit", 5000.0),
        ("turnpoint", "enter", 1000.0),
        ("goal", "enter", 400.0),
    ]


def test_list_tasks_orders_dated_tasks_oldest_first_with_undated_last() -> None:
    session = _session()
    user = User(username="organizer@example.com", full_name="Organizer", role="organizer")
    event = Event(
        name="Sorted Tasks Event",
        location="Tow Ridge",
        starts_on=date(2026, 5, 1),
        ends_on=date(2026, 5, 7),
        timezone="UTC",
    )
    session.add_all([user, event])
    session.flush()
    session.add_all(
        [
            Task(event_id=event.id, name="Newer", task_date=date(2026, 5, 5)),
            Task(event_id=event.id, name="Practice", task_date=date(2026, 5, 4), is_practice=True),
            Task(event_id=event.id, name="Undated", task_date=None),
            Task(event_id=event.id, name="Older", task_date=date(2026, 5, 2)),
        ]
    )
    session.commit()

    payload = list_tasks(event.id, user=user, session=session)

    assert [task.name for task in payload] == ["Practice", "Older", "Newer", "Undated"]


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
        task_type="race_to_goal_with_gates",
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
    assert response.task_type == "race_to_goal_with_gates"
    assert response.task_start_time == "13:30:00"
    assert response.task_finish_time == "17:45:00"
    assert response.start_open_time == "14:00:00"
    assert response.start_close_time == "16:00:00"
    assert response.start_gate_count == 3
    assert response.start_gate_interval_seconds == 900
    assert response.points[0].direction == "enter"


def test_task_response_maps_legacy_task_types_to_new_labels() -> None:
    session = _session()
    event = Event(
        name="Legacy Types Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add(event)
    session.flush()

    task = Task(event_id=event.id, name="Legacy Task", task_type="speedrun")
    session.add(task)
    session.commit()

    response = _task_response(session, task)

    assert response.task_type == "elapsed_time"


def test_elapsed_task_response_uses_task_start_as_effective_start_open() -> None:
    session = _session()
    event = Event(
        name="Elapsed Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add(event)
    session.flush()

    task = Task(
        event_id=event.id,
        name="Elapsed Task",
        task_type="elapsed_time",
        task_start_time="13:30:00",
        start_open_time="14:30:00",
    )
    session.add(task)
    session.commit()

    response = _task_response(session, task)

    assert response.task_type == "elapsed_time"
    assert response.task_start_time == "13:30:00"
    assert response.start_open_time == "13:30:00"


def test_elapsed_task_update_clears_stale_start_open_storage() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin")
    event = Event(
        name="Elapsed Update Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add_all([admin, event])
    session.flush()
    task = Task(
        event_id=event.id,
        name="Elapsed Task",
        task_type="elapsed_time",
        task_start_time="13:30:00",
        start_open_time="14:30:00",
    )
    session.add(task)
    session.commit()

    response = update_task(
        task.id,
        TaskInput(
            name="Elapsed Task",
            task_type="elapsed_time",
            task_start_time="13:30:00",
            start_open_time="14:30:00",
            points=[],
        ),
        admin=admin,
        session=session,
    )

    session.refresh(task)
    assert task.start_open_time is None
    assert response.start_open_time == "13:30:00"


def test_task_response_normalizes_legacy_race_to_goal_to_gated_race() -> None:
    session = _session()
    event = Event(
        name="Legacy Race Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add(event)
    session.flush()

    task = Task(event_id=event.id, name="Legacy Race Task", task_type="race_to_goal")
    session.add(task)
    session.commit()

    response = _task_response(session, task)

    assert response.task_type == "race_to_goal_with_gates"


def test_delete_task_removes_task_and_points() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    event = Event(
        name="Delete Task Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add_all([admin, event])
    session.flush()

    task = Task(event_id=event.id, name="Task 9")
    session.add(task)
    session.flush()
    session.add(
        TaskPoint(
            task_id=task.id,
            position=1,
            point_type="goal",
            radius_m=400,
            turnpoint_id=None,
            name="Goal",
            latitude=38.0,
            longitude=-75.0,
        )
    )
    session.commit()

    delete_task(task.id, admin, session)

    assert session.get(Task, task.id) is None
    assert session.query(TaskPoint).filter(TaskPoint.task_id == task.id).count() == 0


def test_unpublish_task_marks_task_as_draft() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    event = Event(
        name="Publish Event",
        location="Tow Ridge",
        starts_on=date(2026, 3, 18),
        ends_on=date(2026, 3, 19),
        timezone="America/New_York",
    )
    session.add_all([admin, event])
    session.flush()

    task = Task(event_id=event.id, name="Task 3", status="published", published_at=datetime(2026, 3, 18, tzinfo=UTC))
    session.add(task)
    session.commit()

    response = unpublish_task(task.id, admin, session)

    assert response.status == "draft"
    assert response.published_at is None
    refreshed = session.get(Task, task.id)
    assert refreshed is not None
    assert refreshed.status == "draft"
    assert refreshed.published_at is None
