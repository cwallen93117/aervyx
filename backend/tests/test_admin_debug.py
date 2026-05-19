from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, MeshDevice, Pilot, User
from app.routers.admin_debug import admin_debug_status


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_admin_debug_status_lists_registered_mesh_device_without_recent_position() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    owner = User(username="charles@example.com", full_name="Charles Allen", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, owner])
    session.flush()
    owner.pilot_id = pilot.id
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="!abc123",
            label="Charles tracker",
            purpose="tracking",
            is_active=True,
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    devices = payload["registered_mesh_devices"]
    assert len(devices) == 1
    assert devices[0]["owner_user_id"] == owner.id
    assert devices[0]["owner_name"] == "Charles Allen"
    assert devices[0]["owner_pilot_id"] == pilot.id
    assert devices[0]["device_id"] == "!abc123"
    assert devices[0]["label"] == "Charles tracker"
    assert devices[0]["is_connected"] is False
    assert devices[0]["last_seen_at"] is None
    assert devices[0]["last_position"] is None


def test_admin_debug_status_populates_connected_mesh_latest_position() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    owner = User(username="charles@example.com", full_name="Charles Allen", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, owner])
    session.flush()
    owner.pilot_id = pilot.id
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="!abc123",
            label="Charles tracker",
            purpose="tracking",
            is_active=True,
        )
    )
    session.add(
        LivePosition(
            pilot_id=pilot.id,
            task_id=None,
            lat=35.12345,
            lon=-82.54321,
            alt=1234.5,
            speed=42.0,
            heading=271.0,
            accuracy=None,
            timestamp=datetime.now(UTC) - timedelta(seconds=10),
            source="mqtt_gateway",
            device_id="!abc123",
            battery_level=87,
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    device = payload["registered_mesh_devices"][0]
    assert device["is_connected"] is True
    assert device["last_seen_at"] is not None
    assert device["battery_level"] == 87
    assert device["source"] == "mqtt_gateway"
    assert device["last_position"] == {
        "lat": 35.12345,
        "lon": -82.54321,
        "alt": 1234.5,
        "speed": 42.0,
        "heading": 271.0,
    }
