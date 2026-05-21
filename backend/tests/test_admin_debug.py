from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, User
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
    assert devices[0]["mesh_status"] == "never_seen"
    assert devices[0]["last_seen_at"] is None
    assert devices[0]["last_packet_type"] is None
    assert devices[0]["packet_count"] == 0
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
    assert device["mesh_status"] == "live"
    assert device["last_seen_at"] is not None
    assert device["last_packet_type"] == "POSITION_APP"
    assert device["battery_level"] == 87
    assert device["source"] == "mqtt_gateway"
    assert device["last_position"] == {
        "lat": 35.12345,
        "lon": -82.54321,
        "alt": 1234.5,
        "speed": 42.0,
        "heading": 271.0,
    }


def test_admin_debug_status_classifies_mesh_packet_statuses() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Owner", role="pilot")
    session.add_all([admin, owner])
    session.flush()
    for device_id in ["!live", "!stale", "!offline", "!encrypted", "!never"]:
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=device_id,
                label=device_id,
                purpose="tracking",
                is_active=True,
            )
        )
    session.add_all(
        [
            MeshNodeStatus(
                device_id="!live",
                last_seen_at=now - timedelta(minutes=2),
                last_packet_type="NODEINFO_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!gateway",
                packet_count=3,
            ),
            MeshNodeStatus(
                device_id="!stale",
                last_seen_at=now - timedelta(minutes=30),
                last_packet_type="TELEMETRY_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!gateway",
                packet_count=2,
            ),
            MeshNodeStatus(
                device_id="!offline",
                last_seen_at=now - timedelta(hours=7),
                last_packet_type="NEIGHBORINFO_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!gateway",
                packet_count=1,
            ),
            MeshNodeStatus(
                device_id="!encrypted",
                last_seen_at=now - timedelta(minutes=3),
                last_packet_type="ENCRYPTED_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!gateway",
                packet_count=4,
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)
    by_device = {device["device_id"]: device for device in payload["registered_mesh_devices"]}

    assert by_device["!live"]["mesh_status"] == "live"
    assert by_device["!live"]["is_connected"] is True
    assert by_device["!stale"]["mesh_status"] == "stale"
    assert by_device["!stale"]["is_connected"] is False
    assert by_device["!offline"]["mesh_status"] == "offline"
    assert by_device["!encrypted"]["mesh_status"] == "live"
    assert by_device["!encrypted"]["last_packet_type"] == "ENCRYPTED_APP"
    assert by_device["!never"]["mesh_status"] == "never_seen"
    assert by_device["!live"]["last_gateway_id"] == "!gateway"
    assert by_device["!live"]["packet_count"] == 3
