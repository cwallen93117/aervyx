from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Event, IGCUpload, LivePosition, Pilot, SiteSettings, Task, TrackPoint, TrackingSession, User
from app.services import tracking


def _session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(tracking, "SessionLocal", factory)
    return factory


def test_prune_old_live_positions_keeps_only_current_day_by_event_timezone(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime(2026, 5, 10, 4, 30, tzinfo=UTC)

    with factory() as session:
        eastern_event = Event(
            name="Eastern Open",
            location="Ridge",
            starts_on=date(2026, 5, 9),
            ends_on=date(2026, 5, 10),
            timezone="America/New_York",
        )
        pacific_event = Event(
            name="Pacific Open",
            location="Coast",
            starts_on=date(2026, 5, 9),
            ends_on=date(2026, 5, 10),
            timezone="Pacific",
        )
        invalid_zone_event = Event(
            name="Fallback Open",
            location="Somewhere",
            starts_on=date(2026, 5, 9),
            ends_on=date(2026, 5, 10),
            timezone="Not/AZone",
        )
        pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
        user = User(username="ari@example.com", full_name="Ari Sky", role="pilot")
        session.add_all([eastern_event, pacific_event, invalid_zone_event, pilot, user])
        session.flush()
        eastern_task = Task(event_id=eastern_event.id, name="Eastern Task", task_date=date(2026, 5, 10), status="active")
        pacific_task = Task(event_id=pacific_event.id, name="Pacific Task", task_date=date(2026, 5, 10), status="active")
        invalid_zone_task = Task(event_id=invalid_zone_event.id, name="Fallback Task", task_date=date(2026, 5, 10), status="active")
        session.add_all([eastern_task, pacific_task, invalid_zone_task])
        session.flush()
        upload = IGCUpload(
            event_id=eastern_event.id,
            task_id=eastern_task.id,
            pilot_id=pilot.id,
            uploaded_by_user_id=user.id,
            filename="ari.igc",
            sha256="a" * 64,
            stored_path="/tmp/ari.igc",
            metadata_json={},
        )
        session.add(upload)
        session.flush()
        session.add(
            TrackPoint(
                upload_id=upload.id,
                sequence=1,
                recorded_at=now - timedelta(days=5),
                latitude=34.0,
                longitude=-119.0,
                pressure_altitude_m=1000,
                gps_altitude_m=1010,
            )
        )
        session.add_all(
            [
                LivePosition(
                    task_id=eastern_task.id,
                    lat=34.0,
                    lon=-119.0,
                    timestamp=datetime(2026, 5, 10, 3, 59, tzinfo=UTC),
                    source="app",
                    device_id="eastern-yesterday",
                ),
                LivePosition(
                    task_id=eastern_task.id,
                    lat=34.1,
                    lon=-119.1,
                    timestamp=datetime(2026, 5, 10, 4, 1, tzinfo=UTC),
                    source="mqtt_gateway",
                    device_id="eastern-today",
                ),
                LivePosition(
                    task_id=eastern_task.id,
                    lat=34.2,
                    lon=-119.2,
                    timestamp=datetime(2026, 5, 11, 4, 0, tzinfo=UTC),
                    source="mesh_relay",
                    device_id="eastern-tomorrow",
                ),
                LivePosition(
                    task_id=pacific_task.id,
                    lat=34.3,
                    lon=-119.3,
                    timestamp=datetime(2026, 5, 10, 3, 59, tzinfo=UTC),
                    source="other",
                    device_id="pacific-today",
                ),
                LivePosition(
                    task_id=pacific_task.id,
                    lat=34.4,
                    lon=-119.4,
                    timestamp=datetime(2026, 5, 9, 6, 59, tzinfo=UTC),
                    source=None,
                    device_id="pacific-yesterday",
                ),
                LivePosition(
                    lat=34.5,
                    lon=-119.5,
                    timestamp=datetime(2026, 5, 10, 0, 1, tzinfo=UTC),
                    source="app",
                    device_id="taskless-utc-today",
                ),
                LivePosition(
                    lat=34.6,
                    lon=-119.6,
                    timestamp=datetime(2026, 5, 9, 23, 59, tzinfo=UTC),
                    source="app",
                    device_id="taskless-utc-yesterday",
                ),
                LivePosition(
                    task_id=invalid_zone_task.id,
                    lat=34.7,
                    lon=-119.7,
                    timestamp=datetime(2026, 5, 10, 0, 1, tzinfo=UTC),
                    source="app",
                    device_id="invalid-zone-utc-today",
                ),
                LivePosition(
                    task_id=invalid_zone_task.id,
                    lat=34.8,
                    lon=-119.8,
                    timestamp=datetime(2026, 5, 9, 23, 59, tzinfo=UTC),
                    source="app",
                    device_id="invalid-zone-utc-yesterday",
                ),
            ]
        )
        session.commit()

    assert tracking.prune_old_live_positions(now=now) == 5

    with factory() as session:
        remaining_devices = {
            position.device_id
            for position in session.scalars(select(LivePosition).order_by(LivePosition.device_id)).all()
        }
        assert remaining_devices == {
            "eastern-today",
            "invalid-zone-utc-today",
            "pacific-today",
            "taskless-utc-today",
        }
        assert session.scalar(select(TrackPoint)) is not None


def test_prune_old_live_positions_skips_when_site_setting_disabled(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)

    with factory() as session:
        session.add(SiteSettings(id=1, live_position_pruning_enabled=False))
        session.add(
            LivePosition(
                lat=34.0,
                lon=-119.0,
                timestamp=now - timedelta(days=1),
                source="app",
                device_id="old-but-kept",
            )
        )
        session.commit()

    assert tracking.prune_old_live_positions(now=now) == 0

    with factory() as session:
        assert session.scalar(select(LivePosition).where(LivePosition.device_id == "old-but-kept")) is not None


def test_delete_all_live_tracking_data_keeps_non_live_records(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)

    with factory() as session:
        pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
        user = User(username="ari@example.com", full_name="Ari Sky", role="pilot")
        session.add_all([pilot, user])
        session.flush()
        session.add_all(
            [
                LivePosition(pilot_id=pilot.id, lat=34.0, lon=-119.0, timestamp=now, source="app", device_id="live-1"),
                LivePosition(pilot_id=pilot.id, lat=34.1, lon=-119.1, timestamp=now, source="mqtt_gateway", device_id="live-2"),
                TrackingSession(pilot_id=pilot.id, user_id=user.id, is_active=True, position_count=2),
            ]
        )
        session.commit()

        result = tracking.delete_all_live_tracking_data(session)
        assert result == {"deleted_positions": 2, "deleted_sessions": 1}
        assert session.scalars(select(LivePosition)).all() == []
        assert session.scalars(select(TrackingSession)).all() == []
        assert session.scalar(select(Pilot).where(Pilot.id == pilot.id)) is not None
        assert session.scalar(select(User).where(User.id == user.id)) is not None


def test_current_day_history_defaults_to_all_retained_points_and_allows_narrowing(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)

    with factory() as session:
        event = Event(
            name="History Open",
            location="Ridge",
            starts_on=date(2026, 5, 10),
            ends_on=date(2026, 5, 10),
            timezone="UTC",
        )
        pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
        session.add_all([event, pilot])
        session.flush()
        task = Task(event_id=event.id, name="Task 1", task_date=date(2026, 5, 10), status="active")
        session.add(task)
        session.flush()
        session.add_all(
            [
                LivePosition(
                    task_id=task.id,
                    pilot_id=pilot.id,
                    lat=34.0,
                    lon=-119.0,
                    timestamp=now - timedelta(hours=2),
                    source="app",
                    device_id="today-older-than-60-minutes",
                ),
                LivePosition(
                    task_id=task.id,
                    pilot_id=pilot.id,
                    lat=34.1,
                    lon=-119.1,
                    timestamp=now - timedelta(minutes=30),
                    source="app",
                    device_id="today-recent",
                ),
                LivePosition(
                    task_id=task.id,
                    pilot_id=pilot.id,
                    lat=34.2,
                    lon=-119.2,
                    timestamp=now - timedelta(days=1),
                    source="app",
                    device_id="yesterday",
                ),
            ]
        )
        session.commit()

        default_rows = tracking.get_position_history_for_pilots(session, [pilot.id], now=now)
        assert [row["device_id"] for row in default_rows] == [
            "today-older-than-60-minutes",
            "today-recent",
        ]

        narrowed_rows = tracking.get_position_history_for_pilots(session, [pilot.id], minutes=60, now=now)
        assert [row["device_id"] for row in narrowed_rows] == ["today-recent"]

        limited_rows = tracking.get_position_history_for_pilots(session, [pilot.id], limit=1, now=now)
        assert [row["device_id"] for row in limited_rows] == ["today-older-than-60-minutes"]
