import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import LivePosition, Pilot, User
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


def test_prune_old_mqtt_positions_only_deletes_expired_mqtt_rows(monkeypatch) -> None:
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
                    source="app",
                    device_id="app-device",
                ),
                LivePosition(
                    lat=34.2,
                    lon=-119.2,
                    timestamp=now - timedelta(days=1),
                    source="mqtt_gateway",
                    device_id="!recent-mqtt",
                ),
            ]
        )
        session.commit()

    assert mqtt_subscriber.prune_old_mqtt_positions(retention_days=2) == 1

    with factory() as session:
        remaining = session.scalars(select(LivePosition).order_by(LivePosition.device_id)).all()
        assert [position.device_id for position in remaining] == ["!recent-mqtt", "app-device"]
