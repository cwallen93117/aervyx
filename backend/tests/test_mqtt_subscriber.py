import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import LivePosition, MeshDevice, Pilot, User
from app.services import mqtt_subscriber


def _session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    monkeypatch.setattr(mqtt_subscriber, "SessionLocal", factory)
    return factory


def _position_payload(device_id: str) -> bytes:
    return json.dumps(
        {
            "latitude": 34.42,
            "longitude": -119.70,
            "altitude": 510,
            "device_id": device_id,
        }
    ).encode()


def test_mqtt_drops_positions_for_unregistered_devices(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)

    mqtt_subscriber._handle_message(_position_payload("!unassigned"))

    with factory() as session:
        assert session.scalar(select(LivePosition)) is None


def test_mqtt_stores_positions_for_registered_pilot_devices(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        pilot = Pilot(first_name="Riley", last_name="Ridge", email="riley@example.com")
        session.add(pilot)
        session.flush()
        pilot_id = pilot.id
        session.add(
            User(
                username="riley@example.com",
                full_name="Riley Ridge",
                role="pilot",
                pilot_id=pilot_id,
                mesh_device_id="!registered",
            )
        )
        session.flush()
        user = session.scalar(select(User).where(User.username == "riley@example.com"))
        session.add(
            MeshDevice(
                owner_user_id=user.id,
                device_id="!registered",
                label="Riley tracker",
                purpose="tracking",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(_position_payload("!registered"))

    with factory() as session:
        position = session.scalar(select(LivePosition))
        assert position is not None
        assert position.device_id == "!registered"
        assert position.pilot_id == pilot_id
        assert position.source == "mqtt_gateway"


def test_mqtt_stores_positions_for_registered_stationary_nodes(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        session.add(
            User(
                username="relay-node",
                full_name="Relay Node",
                role="pilot",
                profile_type="stationary_node",
                mesh_device_id="!relay",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(_position_payload("!relay"))

    with factory() as session:
        position = session.scalar(select(LivePosition))
        assert position is not None
        assert position.device_id == "!relay"
        assert position.pilot_id is None
        assert position.source == "mqtt_gateway"


def test_mqtt_stores_registered_nontracking_devices_without_pilot(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        owner = User(username="driver@example.com", full_name="Driver One", role="pilot")
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!driverwifi",
                label="Driver gateway",
                purpose="driver_wifi",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(_position_payload("!driverwifi"))

    with factory() as session:
        position = session.scalar(select(LivePosition))
        assert position is not None
        assert position.device_id == "!driverwifi"
        assert position.pilot_id is None
        assert position.source == "mqtt_gateway"


def test_registered_mesh_device_reader_returns_only_active_assignments(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        active = User(username="active", full_name="Active", role="pilot", mesh_device_id="!active")
        inactive = User(username="inactive", full_name="Inactive", role="pilot", mesh_device_id="!inactive", is_active=False)
        owner = User(username="owner", full_name="Owner", role="pilot")
        session.add_all(
            [
                active,
                inactive,
                User(username="empty", full_name="Empty", role="pilot", mesh_device_id=""),
                User(username="none", full_name="None", role="pilot"),
                owner,
            ]
        )
        session.flush()
        session.add_all(
            [
                MeshDevice(owner_user_id=owner.id, device_id="!base", label="Base", purpose="base_station"),
                MeshDevice(owner_user_id=inactive.id, device_id="!inactive-device", label="Inactive", purpose="driver_wifi"),
                MeshDevice(owner_user_id=owner.id, device_id="!disabled", label="Disabled", purpose="relay", is_active=False),
            ]
        )
        session.commit()

    assert mqtt_subscriber._read_registered_mesh_device_ids_from_db() == ["!active", "!base"]


def test_prune_old_mqtt_positions_only_deletes_expired_mesh_rows(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    now = datetime.now(UTC)
    with factory() as session:
        session.add_all(
            [
                LivePosition(
                    lat=34.0,
                    lon=-119.0,
                    timestamp=now - timedelta(days=3),
                    source="mqtt_gateway",
                    device_id="!old-mqtt",
                ),
                LivePosition(
                    lat=34.1,
                    lon=-119.1,
                    timestamp=now - timedelta(days=3),
                    source="mesh_relay",
                    device_id="!old-relay",
                ),
                LivePosition(
                    lat=34.2,
                    lon=-119.2,
                    timestamp=now - timedelta(days=3),
                    source="app",
                    device_id="app-device",
                ),
                LivePosition(
                    lat=34.3,
                    lon=-119.3,
                    timestamp=now - timedelta(days=1),
                    source="mqtt_gateway",
                    device_id="!recent-mqtt",
                ),
            ]
        )
        session.commit()

    assert mqtt_subscriber.prune_old_mqtt_positions(retention_days=2) == 2

    with factory() as session:
        remaining = session.scalars(select(LivePosition).order_by(LivePosition.device_id)).all()
        assert [position.device_id for position in remaining] == ["!recent-mqtt", "app-device"]
