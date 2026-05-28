from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, MeshDevice, MeshNodeStatus, User
from app.routers.tracking import PositionPayload, get_mesh_nodes, post_position


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_mesh_nodes_resolves_gateway_display_name_from_registered_device() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Owner", role="pilot")
    session.add_all([admin, owner])
    session.flush()
    session.add_all(
        [
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!tracker",
                label="Tracker",
                purpose="tracking",
                is_active=True,
            ),
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!gateway",
                label="Ethernet Gateway",
                purpose="relay",
                is_active=True,
            ),
            MeshNodeStatus(
                device_id="!tracker",
                last_seen_at=now - timedelta(minutes=2),
                last_packet_type="TELEMETRY_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!gateway",
                packet_count=7,
            ),
        ]
    )
    session.commit()

    nodes = get_mesh_nodes(minutes=60, admin=admin, session=session)

    tracker = next(node for node in nodes if node.device_id == "!tracker")
    assert tracker.last_gateway_id == "!gateway"
    assert tracker.last_gateway_display_name == "Ethernet Gateway"
    assert tracker.packet_count == 7


def test_mesh_nodes_preserves_mqtt_gateway_for_matching_latest_position() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Tracker Owner", role="pilot")
    gateway_owner = User(username="gateway@example.com", full_name="Gateway Owner", role="pilot")
    session.add_all([admin, owner, gateway_owner])
    session.flush()
    session.add_all(
        [
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!c0ac2c6e",
                label="Tracker #2",
                purpose="tracking",
                is_active=True,
            ),
            MeshDevice(
                owner_user_id=gateway_owner.id,
                device_id="!8ab252ca",
                label="Camper Wired",
                purpose="base_station",
                is_active=True,
            ),
            MeshNodeStatus(
                device_id="!c0ac2c6e",
                last_seen_at=now - timedelta(seconds=2),
                last_packet_type="POSITION_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!8ab252ca",
                last_topic="msh/US/2/e/LongFast/!8ab252ca",
                packet_count=4028,
            ),
            LivePosition(
                lat=40.0547,
                lon=-75.3518,
                timestamp=now,
                source="mqtt_gateway",
                device_id="!c0ac2c6e",
            ),
        ]
    )
    session.commit()

    nodes = get_mesh_nodes(minutes=60, admin=admin, session=session)

    tracker = next(node for node in nodes if node.device_id == "!c0ac2c6e")
    assert tracker.source == "mqtt_gateway"
    assert tracker.last_packet_type == "POSITION_APP"
    assert tracker.last_gateway_id == "!8ab252ca"
    assert tracker.last_gateway_display_name == "Camper Wired"


def test_mesh_nodes_ignores_phone_app_device_ids() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    session.add(admin)
    session.add_all(
        [
            LivePosition(
                lat=35.1,
                lon=-82.5,
                timestamp=now,
                source="app",
                device_id="Unknown",
            ),
            LivePosition(
                lat=35.15,
                lon=-82.55,
                timestamp=now,
                source="mesh_relay",
                device_id="Unknown",
            ),
            LivePosition(
                lat=35.2,
                lon=-82.6,
                timestamp=now,
                source="mesh_relay",
                device_id="!tracker",
            ),
            MeshNodeStatus(
                device_id="Unknown",
                last_seen_at=now,
                last_source="mesh_relay",
                packet_count=1,
            ),
        ]
    )
    session.commit()

    nodes = get_mesh_nodes(minutes=60, admin=admin, session=session)

    assert [node.device_id for node in nodes] == ["!tracker"]


def test_mesh_position_battery_status_uses_position_seen_at() -> None:
    session = _session()
    now = datetime.now(UTC)
    relay_user = User(
        username="relay@example.com",
        full_name="Relay",
        role="pilot",
        mesh_device_id="!gateway",
    )
    session.add(relay_user)
    session.commit()

    response = post_position(
        PositionPayload(
            lat=35.2,
            lon=-82.6,
            timestamp=now,
            source="mesh_relay",
            device_id="!tracker",
            battery_level=87,
        ),
        user=relay_user,
        session=session,
    )

    tracker_status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == "!tracker"))
    assert response.device_id == "!tracker"
    assert tracker_status is not None
    assert tracker_status.battery_level == 87
    assert _utc(tracker_status.battery_level_seen_at) == now
