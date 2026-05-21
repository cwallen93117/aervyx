from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import MeshDevice, MeshNodeStatus, User
from app.routers.tracking import get_mesh_nodes


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


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
