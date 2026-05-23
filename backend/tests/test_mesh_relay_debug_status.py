from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, User
from app.routers.admin_debug import admin_debug_status
from app.routers.tracking import PositionPayload, get_mesh_nodes, post_position


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_mesh_relay_position_updates_sender_and_gateway_status() -> None:
    session = _session()
    now = datetime.now(UTC)
    pilot = Pilot(first_name="Tracker", last_name="Two", email="tracker2@example.com")
    relay_user = User(
        username="tracker1@example.com",
        full_name="Tracker 1",
        role="pilot",
        pilot_id=None,
        mesh_device_id="!c684053e",
    )
    tracked_user = User(username="tracker2@example.com", full_name="Tracker 2", role="pilot", pilot_id=None)
    session.add_all([pilot, relay_user, tracked_user])
    session.flush()
    tracked_user.pilot_id = pilot.id
    session.add_all(
        [
            MeshDevice(
                owner_user_id=relay_user.id,
                device_id="!c684053e",
                label="Tracker 1",
                purpose="tracking",
                is_active=True,
            ),
            MeshDevice(
                owner_user_id=tracked_user.id,
                device_id="!c0ac2c6e",
                label="Tracker #2",
                purpose="tracking",
                is_active=True,
            ),
        ]
    )
    session.commit()

    post_position(
        PositionPayload(
            lat=40.0547,
            lon=-75.3518,
            timestamp=now,
            source="mesh_relay",
            device_id="!c0ac2c6e",
        ),
        user=relay_user,
        session=session,
    )

    sender = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == "!c0ac2c6e"))
    gateway = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == "!c684053e"))
    assert sender is not None
    assert sender.last_seen_at.replace(tzinfo=UTC) == now
    assert sender.last_packet_type == "POSITION_APP"
    assert sender.last_source == "mesh_relay"
    assert sender.last_gateway_id == "!c684053e"
    assert sender.last_topic == "api:/api/track/position"
    assert sender.packet_count == 1
    assert gateway is not None
    assert gateway.last_seen_at.replace(tzinfo=UTC) == now
    assert gateway.last_source == "mesh_relay"
    assert gateway.last_gateway_id == "!c684053e"


def test_debug_payload_prefers_newer_mesh_relay_position_over_stale_mqtt_status() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Tracker Owner", role="pilot")
    session.add_all([admin, owner])
    session.flush()
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="!c684053e",
            label="Tracker 1",
            purpose="tracking",
            is_active=True,
        )
    )
    session.add_all(
        [
            MeshNodeStatus(
                device_id="!c684053e",
                last_seen_at=now - timedelta(hours=1),
                last_packet_type="POSITION_APP",
                last_source="mqtt_gateway",
                last_gateway_id="!c684053e",
                last_topic="msh/US/2/e/LongFast/!c684053e",
                packet_count=10,
            ),
            LivePosition(
                lat=40.0547,
                lon=-75.3518,
                timestamp=now,
                source="mesh_relay",
                device_id="!c684053e",
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)
    device = payload["registered_mesh_devices"][0]
    assert device["mesh_status"] == "live"
    assert device["source"] == "mesh_relay"
    assert device["last_packet_type"] == "POSITION_APP"
    assert device["last_gateway_id"] is None
    assert device["last_seen_at"].replace("+00:00", "") == now.isoformat().replace("+00:00", "")

    nodes = get_mesh_nodes(minutes=60, admin=admin, session=session)
    node = next(item for item in nodes if item.device_id == "!c684053e")
    assert node.mesh_status == "live"
    assert node.source == "mesh_relay"
    assert node.last_packet_type == "POSITION_APP"
    assert node.last_gateway_id is None
