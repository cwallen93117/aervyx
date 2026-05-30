from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, TrackingSession, User
from app.routers.admin_debug import admin_debug_status


def _sqlite_iso(value: datetime) -> str:
    return value.replace(tzinfo=None).isoformat()


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
    seen_at = datetime.now(UTC) - timedelta(seconds=10)
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
            timestamp=seen_at,
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
    assert device["battery_level_seen_at"] == _sqlite_iso(seen_at)
    assert device["source"] == "mqtt_gateway"
    assert device["last_position"] == {
        "lat": 35.12345,
        "lon": -82.54321,
        "alt": 1234.5,
        "speed": 42.0,
        "heading": 271.0,
    }


def test_admin_debug_status_infers_registered_device_pilot_from_latest_position() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    owner = User(username="charles@example.com", full_name="Charles Allen", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, owner])
    session.flush()
    session.add_all(
        [
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!abc123",
                label="Charles tracker",
                purpose="tracking",
                is_active=True,
            ),
            LivePosition(
                pilot_id=pilot.id,
                task_id=None,
                lat=35.12345,
                lon=-82.54321,
                timestamp=now - timedelta(seconds=10),
                source="mqtt_gateway",
                device_id="!abc123",
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    device = payload["registered_mesh_devices"][0]
    assert device["owner_user_id"] == owner.id
    assert device["owner_pilot_id"] == pilot.id


def test_admin_debug_status_omits_mqtt_only_activity_from_phone_sessions() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    owner = User(username="charles@example.com", full_name="Charles Allen", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, owner])
    session.flush()
    owner.pilot_id = pilot.id
    session.add_all(
        [
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!abc123",
                label="Tracker",
                purpose="tracking",
                is_active=True,
            ),
            TrackingSession(
                pilot_id=pilot.id,
                task_id=None,
                started_at=now - timedelta(minutes=5),
                last_seen_at=now - timedelta(seconds=5),
                is_active=True,
                position_count=1,
            ),
            LivePosition(
                pilot_id=pilot.id,
                task_id=None,
                lat=40.05484,
                lon=-75.35188,
                alt=None,
                speed=None,
                heading=0,
                accuracy=None,
                timestamp=now - timedelta(seconds=5),
                source="mqtt_gateway",
                device_id="!abc123",
                battery_level=None,
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert payload["active_sessions"] == []
    device = payload["registered_mesh_devices"][0]
    assert device["device_id"] == "!abc123"
    assert device["mesh_status"] == "live"
    assert device["source"] == "mqtt_gateway"


def test_admin_debug_status_reports_battery_age_separately_from_last_heard() -> None:
    session = _session()
    now = datetime.now(UTC)
    battery_seen_at = now - timedelta(minutes=30)
    last_seen_at = now - timedelta(seconds=5)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Tracker Owner", role="pilot")
    session.add_all([admin, owner])
    session.flush()
    session.add_all(
        [
            MeshDevice(
                owner_user_id=owner.id,
                device_id="!abc123",
                label="Tracker",
                purpose="tracking",
                is_active=True,
            ),
            MeshNodeStatus(
                device_id="!abc123",
                last_seen_at=last_seen_at,
                last_packet_type="POSITION_APP",
                last_source="mqtt_gateway",
                packet_count=10,
                battery_level=71,
                battery_level_seen_at=battery_seen_at,
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    device = payload["registered_mesh_devices"][0]
    assert device["battery_level"] == 71
    assert device["battery_level_seen_at"] == _sqlite_iso(battery_seen_at)
    assert device["last_seen_at"] == _sqlite_iso(last_seen_at)


def test_admin_debug_status_keeps_phone_session_separate_from_newer_mqtt_position() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    owner = User(username="charles@example.com", full_name="Charles Allen", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, owner])
    session.flush()
    owner.pilot_id = pilot.id
    session.add(
        TrackingSession(
            pilot_id=pilot.id,
            task_id=None,
            started_at=now - timedelta(minutes=10),
            last_seen_at=now - timedelta(seconds=5),
            is_active=True,
            position_count=2,
        )
    )
    session.add_all(
        [
            LivePosition(
                pilot_id=pilot.id,
                task_id=None,
                lat=40.1,
                lon=-75.1,
                alt=300,
                speed=12,
                heading=None,
                accuracy=None,
                timestamp=now - timedelta(minutes=2),
                source="app",
                device_id="app-device-should-not-render",
                battery_level=44,
            ),
            LivePosition(
                pilot_id=pilot.id,
                task_id=None,
                lat=40.05484,
                lon=-75.35188,
                alt=350,
                speed=14,
                heading=0,
                accuracy=None,
                timestamp=now - timedelta(seconds=5),
                source="mqtt_gateway",
                device_id="!abc123",
                battery_level=80,
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert len(payload["active_sessions"]) == 1
    phone = payload["active_sessions"][0]
    assert phone["device_id"] is None
    assert phone["source"] == "app"
    assert phone["battery_level"] == 44
    assert phone["battery_level_seen_at"] == _sqlite_iso(now - timedelta(minutes=2))
    assert phone["position_count"] == 1
    assert phone["positions_last_60s"] == 0
    assert phone["is_online"] is False
    assert phone["last_position"] == {
        "lat": 40.1,
        "lon": -75.1,
        "alt": 300.0,
        "speed": 12.0,
    }
    assert phone["has_mesh"] is True


def test_admin_debug_status_uses_phone_battery_seen_at() -> None:
    session = _session()
    now = datetime.now(UTC)
    battery_seen_at = now - timedelta(seconds=45)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com")
    session.add_all([admin, pilot])
    session.flush()
    session.add(
        TrackingSession(
            pilot_id=pilot.id,
            task_id=None,
            started_at=now - timedelta(minutes=10),
            last_seen_at=now,
            is_active=True,
            position_count=1,
        )
    )
    session.add(
        LivePosition(
            pilot_id=pilot.id,
            task_id=None,
            lat=40.1,
            lon=-75.1,
            alt=300,
            speed=12,
            heading=None,
            accuracy=None,
            timestamp=now,
            source="app",
            battery_level=44,
            battery_level_seen_at=battery_seen_at,
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    phone = payload["active_sessions"][0]
    assert phone["battery_level"] == 44
    assert phone["battery_level_seen_at"] == _sqlite_iso(battery_seen_at)


def test_admin_debug_status_lists_recent_phone_position_without_tracking_session() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Jeff", last_name="Chipman", email="jeff@example.com")
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, user])
    session.flush()
    user.pilot_id = pilot.id
    session.add_all(
        [
            LivePosition(
                pilot_id=pilot.id,
                user_id=user.id,
                task_id=None,
                lat=40.25,
                lon=-75.25,
                alt=402,
                speed=8,
                heading=None,
                accuracy=None,
                timestamp=now - timedelta(seconds=5),
                source="app",
                battery_level=62,
            ),
            LivePosition(
                pilot_id=pilot.id,
                user_id=user.id,
                task_id=None,
                lat=40.24,
                lon=-75.24,
                alt=398,
                speed=7,
                heading=None,
                accuracy=None,
                timestamp=now - timedelta(seconds=10),
                source="app",
                battery_level=63,
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert len(payload["active_sessions"]) == 1
    phone = payload["active_sessions"][0]
    assert phone["pilot_id"] == pilot.id
    assert phone["user_id"] == user.id
    assert phone["pilot_name"] == "Jeff Chipman"
    assert phone["source"] == "app"
    assert phone["position_count"] == 2
    assert phone["positions_last_60s"] == 2
    assert phone["is_online"] is True
    assert phone["last_position"] == {
        "lat": 40.25,
        "lon": -75.25,
        "alt": 402.0,
        "speed": 8.0,
    }


def test_admin_debug_status_ignores_old_phone_position_without_tracking_session() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Jeff", last_name="Chipman", email="jeff@example.com")
    user = User(username="jeff@example.com", full_name="Jeff Chipman", role="pilot", pilot_id=None)
    session.add_all([admin, pilot, user])
    session.flush()
    user.pilot_id = pilot.id
    session.add(
        LivePosition(
            pilot_id=pilot.id,
            user_id=user.id,
            task_id=None,
            lat=40.25,
            lon=-75.25,
            timestamp=now - timedelta(hours=7),
            source="app",
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert payload["active_sessions"] == []


def test_admin_debug_status_names_user_subject_phone_session() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    driver = User(
        username="driver@example.com",
        full_name="Dana Driver",
        role="pilot",
        profile_type="driver",
    )
    other = User(
        username="other@example.com",
        full_name="Other Driver",
        role="pilot",
        profile_type="driver",
    )
    session.add_all([admin, driver, other])
    session.flush()
    session.add(
        TrackingSession(
            user_id=driver.id,
            pilot_id=None,
            task_id=None,
            started_at=now - timedelta(minutes=5),
            last_seen_at=now - timedelta(seconds=5),
            is_active=True,
            position_count=1,
        )
    )
    session.add_all(
        [
            LivePosition(
                user_id=driver.id,
                pilot_id=None,
                task_id=None,
                lat=35.1,
                lon=-82.5,
                timestamp=now - timedelta(seconds=5),
                source="app",
            ),
            LivePosition(
                user_id=other.id,
                pilot_id=None,
                task_id=None,
                lat=36.1,
                lon=-83.5,
                timestamp=now - timedelta(seconds=4),
                source="app",
            ),
        ]
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert len(payload["active_sessions"]) == 2
    phone = next(item for item in payload["active_sessions"] if item["user_id"] == driver.id)
    assert phone["pilot_id"] is None
    assert phone["user_id"] == driver.id
    assert phone["pilot_name"] == "Dana Driver"
    assert phone["profile_type"] == "driver"
    assert phone["position_count"] == 1
    assert phone["last_position"] == {
        "lat": 35.1,
        "lon": -82.5,
        "alt": None,
        "speed": None,
    }


def test_admin_debug_status_omits_orphan_active_session() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    session.add(admin)
    session.add(
        TrackingSession(
            pilot_id=None,
            user_id=None,
            task_id=None,
            started_at=now - timedelta(minutes=5),
            last_seen_at=now - timedelta(seconds=5),
            is_active=True,
            position_count=1,
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)

    assert payload["active_sessions"] == []


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
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="!gateway",
            label="Ethernet Gateway",
            purpose="relay",
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
    assert by_device["!live"]["last_gateway_display_name"] == "Ethernet Gateway"
    assert by_device["!live"]["packet_count"] == 3


def test_admin_debug_status_preserves_mqtt_gateway_for_matching_latest_position() -> None:
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

    payload = admin_debug_status(admin, session)
    by_device = {device["device_id"]: device for device in payload["registered_mesh_devices"]}

    assert by_device["!c0ac2c6e"]["source"] == "mqtt_gateway"
    assert by_device["!c0ac2c6e"]["last_packet_type"] == "POSITION_APP"
    assert by_device["!c0ac2c6e"]["last_gateway_id"] == "!8ab252ca"
    assert by_device["!c0ac2c6e"]["last_gateway_display_name"] == "Camper Wired"


def test_admin_debug_status_matches_legacy_bare_hex_device_id() -> None:
    session = _session()
    now = datetime.now(UTC)
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    owner = User(username="owner@example.com", full_name="Owner", role="pilot")
    session.add_all([admin, owner])
    session.flush()
    session.add(
        MeshDevice(
            owner_user_id=owner.id,
            device_id="435a8b00",
            label="Tahoe Supreme",
            purpose="tracking",
            is_active=True,
        )
    )
    session.add(
        MeshNodeStatus(
            device_id="!435a8b00",
            last_seen_at=now - timedelta(minutes=1),
            last_packet_type="NODEINFO_APP",
            last_source="mqtt_gateway",
            last_gateway_id="!435a8b00",
            packet_count=1,
        )
    )
    session.commit()

    payload = admin_debug_status(admin, session)
    device = payload["registered_mesh_devices"][0]

    assert device["device_id"] == "!435a8b00"
    assert device["mesh_status"] == "live"
    assert device["last_packet_type"] == "NODEINFO_APP"
