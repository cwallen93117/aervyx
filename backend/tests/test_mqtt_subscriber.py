import base64
import json
import os
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta

os.environ.setdefault("APP_SECRET_KEY", "mqtt-subscriber-test-secret-key")

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, SiteSettings, User
from app.services import mqtt_subscriber, tracking


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
    monkeypatch.setattr(tracking, "SessionLocal", factory)
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


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        to_write = value & 0x7F
        value >>= 7
        if value:
            out.append(to_write | 0x80)
        else:
            out.append(to_write)
            return bytes(out)


def _field_varint(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 0) + _varint(value)


def _field_bytes(field_number: int, value: bytes) -> bytes:
    return _varint((field_number << 3) | 2) + _varint(len(value)) + value


def _field_fixed32(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 5) + value.to_bytes(4, "little", signed=False)


def _field_sfixed32(field_number: int, value: int) -> bytes:
    return _varint((field_number << 3) | 5) + value.to_bytes(4, "little", signed=True)


def _mesh_envelope(
    from_node: int,
    portnum: int,
    payload: bytes,
    gateway_id: str | None = None,
    decoded_field: int = 4,
) -> bytes:
    data = _field_varint(1, portnum) + _field_bytes(2, payload)
    mesh_packet = _field_fixed32(1, from_node) + _field_bytes(decoded_field, data)
    envelope = _field_bytes(1, mesh_packet) + _field_bytes(2, b"LongFast")
    if gateway_id:
        envelope += _field_bytes(3, gateway_id.encode())
    return envelope


def _encrypted_mesh_envelope(
    from_node: int,
    portnum: int,
    payload: bytes,
    *,
    psk: bytes,
    packet_id: int = 1234,
    gateway_id: str | None = None,
) -> bytes:
    data = _field_varint(1, portnum) + _field_bytes(2, payload)
    nonce = packet_id.to_bytes(8, "little") + from_node.to_bytes(4, "little") + b"\x00" * 4
    encryptor = Cipher(algorithms.AES(psk), modes.CTR(nonce)).encryptor()
    encrypted = encryptor.update(data) + encryptor.finalize()
    mesh_packet = (
        _field_fixed32(1, from_node)
        + _field_varint(3, 0)
        + _field_bytes(5, encrypted)
        + _field_fixed32(6, packet_id)
    )
    envelope = _field_bytes(1, mesh_packet) + _field_bytes(2, b"LongFast")
    if gateway_id:
        envelope += _field_bytes(3, gateway_id.encode())
    return envelope


def _nodeinfo_payload(device_id: str, long_name: str = "Tracker One", short_name: str = "TRK") -> bytes:
    return (
        _field_bytes(1, device_id.encode())
        + _field_bytes(2, long_name.encode())
        + _field_bytes(3, short_name.encode())
    )


def _telemetry_payload(battery_level: int) -> bytes:
    return _field_bytes(2, _field_varint(1, battery_level))


def _protobuf_position_payload(lat: float = 34.42, lon: float = -119.70, altitude: int = 510) -> bytes:
    return (
        _field_sfixed32(1, int(lat * 1e7))
        + _field_sfixed32(2, int(lon * 1e7))
        + _field_varint(3, altitude)
    )


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


def test_mqtt_stores_official_protobuf_position_field_four(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    device_id = "!00abc123"
    with factory() as session:
        pilot = Pilot(first_name="Owner", last_name="One", email="owner@example.com")
        session.add(pilot)
        session.flush()
        owner = User(
            username="owner@example.com",
            full_name="Owner One",
            role="pilot",
            pilot_id=pilot.id,
            mesh_device_id=device_id,
        )
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=device_id,
                label="Owner tracker",
                purpose="tracking",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _mesh_envelope(0x00ABC123, 3, _protobuf_position_payload()),
        topic=f"msh/US/2/e/LongFast/{device_id}",
    )

    with factory() as session:
        position = session.scalar(select(LivePosition))
        status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == device_id))
        assert position is not None
        assert position.device_id == device_id
        assert position.lat == 34.42
        assert position.lon == -119.70
        assert status is not None
        assert status.last_packet_type == "POSITION_APP"


def test_mqtt_records_nodeinfo_status_without_position(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    device_id = "!00abc123"
    with factory() as session:
        owner = User(username="owner@example.com", full_name="Owner One", role="pilot")
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=device_id,
                label="Owner tracker",
                purpose="tracking",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _mesh_envelope(0x00ABC123, 4, _nodeinfo_payload(device_id, "Owner Tracker", "OWN")),
        topic=f"msh/US/2/e/LongFast/{device_id}",
    )

    with factory() as session:
        assert session.scalar(select(LivePosition)) is None
        status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == device_id))
        assert status is not None
        assert status.last_packet_type == "NODEINFO_APP"
        assert status.long_name == "Owner Tracker"
        assert status.short_name == "OWN"
        assert status.packet_count == 1


def test_cloud_vm_mqtt_subscriber_uses_admin_broker(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_enabled=True,
                mqtt_broker_mode="cloud_vm",
                mqtt_host="mqtt-staging.aervyx.net",
                mqtt_port=8883,
                mqtt_tls_enabled=True,
                mqtt_username="fleet",
                mqtt_password="secret",
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()

    monkeypatch.setattr(
        mqtt_subscriber,
        "get_settings",
        lambda: SimpleNamespace(mqtt_host="mosquitto", mqtt_port=1883),
    )

    assert mqtt_subscriber._read_mqtt_config_from_db() == (
        "mqtt-staging.aervyx.net",
        8883,
        "msh",
        "fleet",
        "secret",
        True,
    )


def test_legacy_private_mqtt_subscriber_maps_to_cloud_vm(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_enabled=True,
                mqtt_broker_mode="private",
                mqtt_host="mqtt-staging.aervyx.net",
                mqtt_port=8883,
                mqtt_tls_enabled=True,
                mqtt_username="fleet",
                mqtt_password="secret",
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()

    monkeypatch.setattr(
        mqtt_subscriber,
        "get_settings",
        lambda: SimpleNamespace(mqtt_host="mosquitto", mqtt_port=1883),
    )

    assert mqtt_subscriber._read_mqtt_config_from_db() == (
        "mqtt-staging.aervyx.net",
        8883,
        "msh",
        "fleet",
        "secret",
        True,
    )


def test_local_mosquitto_subscriber_uses_internal_broker(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_enabled=True,
                mqtt_broker_mode="local_mosquitto",
                mqtt_host="192.168.87.51",
                mqtt_port=1883,
                mqtt_tls_enabled=False,
                mqtt_username="fleet",
                mqtt_password="secret",
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()

    monkeypatch.setattr(
        mqtt_subscriber,
        "get_settings",
        lambda: SimpleNamespace(mqtt_host="mosquitto", mqtt_port=1883),
    )

    assert mqtt_subscriber._read_mqtt_config_from_db() == (
        "mosquitto",
        1883,
        "msh",
        None,
        None,
        False,
    )


def test_legacy_public_mqtt_subscriber_maps_to_local_mosquitto(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        session.add(
            SiteSettings(
                id=1,
                mqtt_enabled=True,
                mqtt_broker_mode="public",
                mqtt_host=None,
                mqtt_port=1883,
                mqtt_topic_prefix="msh",
            )
        )
        session.commit()

    monkeypatch.setattr(
        mqtt_subscriber,
        "get_settings",
        lambda: SimpleNamespace(mqtt_host="mosquitto", mqtt_port=1883),
    )

    assert mqtt_subscriber._read_mqtt_config_from_db() == (
        "mosquitto",
        1883,
        "msh",
        None,
        None,
        False,
    )


def test_mqtt_keeps_legacy_field_three_decoded_fallback(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    device_id = "!00abc123"
    with factory() as session:
        owner = User(username="legacy@example.com", full_name="Legacy Owner", role="pilot")
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=device_id,
                label="Legacy tracker",
                purpose="tracking",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _mesh_envelope(
            0x00ABC123,
            4,
            _nodeinfo_payload(device_id, "Legacy Tracker", "LEG"),
            decoded_field=3,
        ),
        topic=f"msh/US/2/e/LongFast/{device_id}",
    )

    with factory() as session:
        status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == device_id))
        assert status is not None
        assert status.last_packet_type == "NODEINFO_APP"
        assert status.long_name == "Legacy Tracker"


def test_mqtt_records_gateway_and_inner_sender_status_separately(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    gateway_id = "!11111111"
    sender_id = "!22222222"
    with factory() as session:
        owner = User(username="gateway@example.com", full_name="Gateway Owner", role="pilot")
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=gateway_id,
                label="Ethernet gateway",
                purpose="base_station",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _mesh_envelope(0x22222222, 67, _telemetry_payload(88), gateway_id=gateway_id),
        topic=f"msh/US/2/e/LongFast/{gateway_id}",
    )

    with factory() as session:
        assert session.scalar(select(LivePosition)) is None
        gateway = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == gateway_id))
        sender = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == sender_id))
        assert gateway is not None
        assert sender is not None
        assert gateway.last_packet_type == "TELEMETRY_APP"
        assert gateway.last_gateway_id == gateway_id
        assert gateway.battery_level is None
        assert sender.last_packet_type == "TELEMETRY_APP"
        assert sender.last_gateway_id == gateway_id
        assert sender.battery_level == 88


def test_mqtt_records_encrypted_status_when_payload_cannot_be_decrypted(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    gateway_id = "!11111111"
    sender_id = "!22222222"
    with factory() as session:
        owner = User(username="gateway@example.com", full_name="Gateway Owner", role="pilot")
        session.add(owner)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=owner.id,
                device_id=gateway_id,
                label="Ethernet gateway",
                purpose="base_station",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _encrypted_mesh_envelope(
            0x22222222,
            67,
            _telemetry_payload(88),
            psk=b"\x23" * 16,
            gateway_id=gateway_id,
        ),
        topic=f"msh/US/2/e/LongFast/{gateway_id}",
    )

    with factory() as session:
        assert session.scalar(select(LivePosition)) is None
        gateway = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == gateway_id))
        sender = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == sender_id))
        assert gateway is not None
        assert sender is not None
        assert gateway.last_packet_type == "ENCRYPTED_APP"
        assert gateway.last_gateway_id == gateway_id
        assert sender.last_packet_type == "ENCRYPTED_APP"
        assert sender.last_gateway_id == gateway_id
        assert sender.battery_level is None


def test_mqtt_decrypts_default_psk_encrypted_position(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    gateway_id = "!11111111"
    sender_id = "!22222222"
    with factory() as session:
        pilot = Pilot(first_name="Riley", last_name="Ridge", email="riley@example.com")
        owner = User(username="riley@example.com", full_name="Riley Ridge", role="pilot")
        gateway_owner = User(username="gateway@example.com", full_name="Gateway Owner", role="pilot")
        session.add_all([pilot, owner, gateway_owner])
        session.flush()
        pilot_id = pilot.id
        owner.pilot_id = pilot.id
        owner.mesh_device_id = sender_id
        session.add_all(
            [
                MeshDevice(
                    owner_user_id=owner.id,
                    device_id=sender_id,
                    label="Riley tracker",
                    purpose="tracking",
                ),
                MeshDevice(
                    owner_user_id=gateway_owner.id,
                    device_id=gateway_id,
                    label="Ethernet gateway",
                    purpose="base_station",
                ),
            ]
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _encrypted_mesh_envelope(
            0x22222222,
            3,
            _protobuf_position_payload(35.12, -82.54, 900),
            psk=mqtt_subscriber._MESHTASTIC_DEFAULT_PSK,
            gateway_id=gateway_id,
        ),
        topic=f"msh/US/2/e/LongFast/{gateway_id}",
    )

    with factory() as session:
        position = session.scalar(select(LivePosition))
        gateway = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == gateway_id))
        sender = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == sender_id))
        assert position is not None
        assert position.device_id == sender_id
        assert position.pilot_id == pilot_id
        assert position.lat == 35.12
        assert position.lon == -82.54
        assert gateway is not None
        assert sender is not None
        assert gateway.last_packet_type == "POSITION_APP"
        assert sender.last_packet_type == "POSITION_APP"
        assert sender.last_gateway_id == gateway_id


def test_mqtt_decrypts_configured_psk_encrypted_position(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    gateway_id = "!11111111"
    sender_id = "!22222222"
    custom_psk = bytes(range(16))
    with factory() as session:
        pilot = Pilot(first_name="Dana", last_name="Drift", email="dana@example.com")
        owner = User(username="dana@example.com", full_name="Dana Drift", role="pilot")
        gateway_owner = User(username="gateway@example.com", full_name="Gateway Owner", role="pilot")
        session.add_all(
            [
                SiteSettings(id=1, mqtt_channel_psk=base64.b64encode(custom_psk).decode("ascii")),
                pilot,
                owner,
                gateway_owner,
            ]
        )
        session.flush()
        pilot_id = pilot.id
        owner.pilot_id = pilot.id
        owner.mesh_device_id = sender_id
        session.add_all(
            [
                MeshDevice(
                    owner_user_id=owner.id,
                    device_id=sender_id,
                    label="Dana tracker",
                    purpose="tracking",
                ),
                MeshDevice(
                    owner_user_id=gateway_owner.id,
                    device_id=gateway_id,
                    label="Ethernet gateway",
                    purpose="base_station",
                ),
            ]
        )
        session.commit()

    mqtt_subscriber._handle_message(
        _encrypted_mesh_envelope(
            0x22222222,
            3,
            _protobuf_position_payload(36.5, -81.25, 1100),
            psk=custom_psk,
            gateway_id=gateway_id,
        ),
        topic=f"msh/US/2/e/LongFast/{gateway_id}",
    )

    with factory() as session:
        position = session.scalar(select(LivePosition))
        sender = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == sender_id))
        assert position is not None
        assert position.device_id == sender_id
        assert position.pilot_id == pilot_id
        assert position.lat == 36.5
        assert position.lon == -81.25
        assert sender is not None
        assert sender.last_packet_type == "POSITION_APP"
        assert sender.last_gateway_id == gateway_id


def test_json_position_matches_legacy_bare_hex_mesh_registration(monkeypatch) -> None:
    factory = _session_factory(monkeypatch)
    with factory() as session:
        pilot = Pilot(first_name="Tahoe", last_name="Supreme", email="tahoe@example.com")
        session.add(pilot)
        session.flush()
        pilot_id = pilot.id
        user = User(
            username="tahoe@example.com",
            full_name="Tahoe Supreme",
            role="pilot",
            pilot_id=pilot_id,
            mesh_device_id="435a8b00",
        )
        session.add(user)
        session.flush()
        session.add(
            MeshDevice(
                owner_user_id=user.id,
                device_id="435a8b00",
                label="Tahoe Supreme",
                purpose="tracking",
            )
        )
        session.commit()

    mqtt_subscriber._handle_message(_position_payload("!435a8b00"), topic="msh/US/2/e/LongFast/!435a8b00")

    with factory() as session:
        position = session.scalar(select(LivePosition).where(LivePosition.device_id == "!435a8b00"))
        status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == "!435a8b00"))

    assert position is not None
    assert position.pilot_id == pilot_id
    assert status is not None
    assert status.last_packet_type == "POSITION_APP"


def test_prune_old_mqtt_positions_delegates_to_all_live_position_retention(monkeypatch) -> None:
    calls: list[int | None] = []

    def fake_prune_old_live_positions(retention_days: int | None = None) -> int:
        calls.append(retention_days)
        return 7

    monkeypatch.setattr(mqtt_subscriber, "prune_old_live_positions", fake_prune_old_live_positions)

    assert mqtt_subscriber.prune_old_mqtt_positions(retention_days=2) == 7
    assert calls == [2]
