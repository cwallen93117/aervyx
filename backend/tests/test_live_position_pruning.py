from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Event, IGCUpload, LivePosition, Pilot, Task, TrackPoint, User
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


def test_prune_old_live_positions_deletes_all_sources_but_keeps_recent_and_igc(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)

    with factory() as session:
        event = Event(
            name="Retention Open",
            location="Ridge",
            starts_on=date(2026, 5, 9),
            ends_on=date(2026, 5, 10),
            timezone="UTC",
        )
        pilot = Pilot(first_name="Ari", last_name="Sky", email="ari@example.com")
        user = User(username="ari@example.com", full_name="Ari Sky", role="pilot")
        session.add_all([event, pilot, user])
        session.flush()
        task = Task(event_id=event.id, name="Task 1", task_date=date(2026, 5, 10), status="active")
        session.add(task)
        session.flush()
        upload = IGCUpload(
            event_id=event.id,
            task_id=task.id,
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
                    lat=34.0,
                    lon=-119.0,
                    timestamp=now - timedelta(days=3),
                    source="app",
                    device_id="old-app",
                ),
                LivePosition(
                    lat=34.1,
                    lon=-119.1,
                    timestamp=now - timedelta(days=3),
                    source="mqtt_gateway",
                    device_id="old-mqtt",
                ),
                LivePosition(
                    lat=34.2,
                    lon=-119.2,
                    timestamp=now - timedelta(days=3),
                    source="mesh_relay",
                    device_id="old-mesh",
                ),
                LivePosition(
                    lat=34.3,
                    lon=-119.3,
                    timestamp=now - timedelta(days=3),
                    source="other",
                    device_id="old-other",
                ),
                LivePosition(
                    lat=34.4,
                    lon=-119.4,
                    timestamp=now - timedelta(days=3),
                    source=None,
                    device_id="old-null-source",
                ),
                LivePosition(
                    lat=34.5,
                    lon=-119.5,
                    timestamp=now - timedelta(days=1),
                    source="app",
                    device_id="recent-app",
                ),
                LivePosition(
                    lat=34.6,
                    lon=-119.6,
                    timestamp=now - timedelta(days=2),
                    source="app",
                    device_id="boundary-app",
                ),
            ]
        )
        session.commit()

    assert tracking.prune_old_live_positions(retention_days=2, now=now) == 5

    with factory() as session:
        remaining_devices = {
            position.device_id
            for position in session.scalars(select(LivePosition).order_by(LivePosition.device_id)).all()
        }
        assert remaining_devices == {"boundary-app", "recent-app"}
        assert session.scalar(select(TrackPoint)) is not None
