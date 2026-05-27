from datetime import UTC, date, datetime
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models import Event, EventPilot, MeshDevice, Pilot, User
from app.routers.auth import (
    admin_set_user_tracking_mesh_device,
    admin_update_user_mesh_device,
    change_password,
    create_mesh_device,
    list_mesh_devices,
    list_users,
    register,
    register_mesh_device,
    update_mesh_device,
    update_settings,
    update_user_account,
)
from app.routers.events import list_events
from app.routers.pilots import assign_existing_pilot, create_pilot, update_pilot
from app.schemas import AccountSettingsUpdate, AdminUserUpdate, MeshDeviceCreate, MeshDeviceRegister, MeshDeviceUpdate, PasswordChangeRequest, PilotUpsert, RegisterRequest
from app.services.tracking import resolve_mesh_device_assignment
from app.services.pilot_identity import repair_pilot_email_identities


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/register",
            "headers": [],
            "client": ("testclient", 50000),
        }
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_register_links_existing_pilot_by_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Casey", last_name="Flyer", email="casey@example.com", competition_number="42")
    session.add(pilot)
    session.commit()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
            _request(),
            RegisterRequest(
                first_name="Casey",
                last_name="Flyer",
                email="casey@example.com",
                password="secret123",
            ),
            session,
        )

    user = session.query(User).filter(User.username == "casey@example.com").one()
    assert response.user.username == "casey@example.com"
    assert response.user.pilot_id == pilot.id
    assert user.pilot_id == pilot.id


def test_register_organizer_creates_user_without_pilot() -> None:
    session = _session()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
            _request(),
            RegisterRequest(
                first_name="Olivia",
                last_name="Meet",
                email="organizer@example.com",
                password="secret123",
                account_role="organizer",
            ),
            session,
        )

    user = session.query(User).filter(User.username == "organizer@example.com").one()
    assert response.user.role == "organizer"
    assert response.user.pilot_id is None
    assert user.profile_type == "driver"


def test_assign_existing_pilot_adds_them_to_event() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, pilot, event])
    session.commit()

    response = assign_existing_pilot(event.id, pilot.id, admin, session)

    assert response.id == pilot.id
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == pilot.id)) is not None


def test_create_pilot_with_email_creates_email_login_user() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    event = Event(name="Spring Open", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    session.add_all([admin, event])
    session.commit()

    response = create_pilot(
        event.id,
        PilotUpsert(
            first_name="New",
            last_name="Pilot",
            email="New.Pilot@Example.com",
            nation="US",
            competition_number="12",
            civl_id=None,
        ),
        admin,
        session,
    )

    user = session.scalar(select(User).where(User.username == "new.pilot@example.com"))
    assert response.email == "new.pilot@example.com"
    assert response.portal_username == "new.pilot@example.com"
    assert user is not None
    assert user.pilot_id == response.id
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == response.id)) is not None


def test_update_portal_only_pilot_to_email_renames_login() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Charles", last_name="Allen", email=None)
    session.add_all([admin, pilot])
    session.flush()
    portal_user = User(username="charles-allen-pilot", full_name="Charles Allen", role="pilot", pilot_id=pilot.id, password_hash="hash")
    session.add(portal_user)
    session.commit()

    response = update_pilot(
        pilot.id,
        PilotUpsert(
            first_name="Charles",
            last_name="Allen",
            email="C.Allen@BTCS.com",
            nation=None,
            competition_number=None,
            civl_id=None,
        ),
        admin,
        session,
    )

    session.refresh(portal_user)
    assert response.id == pilot.id
    assert response.email == "c.allen@btcs.com"
    assert response.portal_username == "c.allen@btcs.com"
    assert portal_user.username == "c.allen@btcs.com"
    assert portal_user.pilot_id == pilot.id
    assert portal_user.is_active is True


def test_assign_existing_pilot_links_matching_email_user() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="c.allen@btcs.com")
    generated_user = User(username="charles-allen-pilot", full_name="Charles Allen", role="pilot", pilot_id=None, password_hash="hash")
    email_user = User(username="c.allen@btcs.com", full_name="Charles Allen", role="pilot", pilot_id=None, password_hash="hash")
    event = Event(name="HC 2025 - myles", location="Myles", starts_on=date(2026, 5, 7), ends_on=date(2026, 5, 9), timezone="UTC")
    session.add_all([admin, pilot, generated_user, email_user, event])
    session.flush()
    generated_user.pilot_id = pilot.id
    session.commit()

    response = assign_existing_pilot(event.id, pilot.id, admin, session)

    session.refresh(email_user)
    session.refresh(generated_user)
    assert response.portal_username == "c.allen@btcs.com"
    assert email_user.pilot_id == pilot.id
    assert generated_user.pilot_id is None
    assert generated_user.is_active is False
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == pilot.id)) is not None


def test_startup_repair_moves_duplicate_event_membership_to_email_identity() -> None:
    session = _session()
    email_pilot = Pilot(first_name="Charles", last_name="Allen", email="c.allen@btcs.com")
    roster_pilot = Pilot(first_name="Charles", last_name="Allen", email="c.allen@btcs.com")
    event = Event(
        name="HC 2025 - myles",
        location="Myles",
        starts_on=date(2026, 5, 7),
        ends_on=date(2026, 5, 9),
        timezone="UTC",
        visibility="participants",
    )
    session.add_all([email_pilot, roster_pilot, event])
    session.flush()
    email_user = User(username="c.allen@btcs.com", full_name="Charles Allen", role="pilot", pilot_id=email_pilot.id, password_hash="hash")
    generated_user = User(username="charles-allen-pilot", full_name="Charles Allen", role="pilot", pilot_id=roster_pilot.id, password_hash="hash")
    session.add_all([email_user, generated_user, EventPilot(event_id=event.id, pilot_id=roster_pilot.id)])
    session.commit()

    repair_pilot_email_identities(session)
    session.commit()

    session.refresh(email_user)
    session.refresh(generated_user)
    session.refresh(roster_pilot)
    assert email_user.pilot_id == email_pilot.id
    assert generated_user.pilot_id is None
    assert generated_user.is_active is False
    assert roster_pilot.email is None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == email_pilot.id)) is not None
    assert session.scalar(select(EventPilot).where(EventPilot.event_id == event.id, EventPilot.pilot_id == roster_pilot.id)) is None
    assert {event.name for event in list_events(user=email_user, session=session)} == {"HC 2025 - myles"}


def test_update_settings_updates_pilot_profile_and_username_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com", nation="US")
    previous_profile_type_updated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    user = User(
        username="robin@example.com",
        full_name="Robin Wing",
        role="pilot",
        password_hash="hash",
        pilot_id=None,
        profile_type_updated_at=previous_profile_type_updated_at,
    )
    session.add_all([pilot, user])
    session.commit()
    user.pilot_id = pilot.id
    session.commit()

    response = update_settings(
        AccountSettingsUpdate(
            username="pilot@example.com",
            full_name="Robin Wing",
            profile_type="driver",
            email="pilot@example.com",
            first_name="Robin",
            last_name="Wing",
            nation="usa",
            competition_number="77",
            civl_id="CIVL-77",
        ),
        user,
        session,
    )

    session.refresh(user)
    session.refresh(pilot)
    assert response.username == "pilot@example.com"
    assert response.profile_type == "driver"
    assert _utc(response.profile_type_updated_at) > previous_profile_type_updated_at
    assert user.username == "pilot@example.com"
    assert user.profile_type == "driver"
    assert _utc(user.profile_type_updated_at) > previous_profile_type_updated_at
    assert pilot.email == "pilot@example.com"
    assert pilot.nation == "USA"
    assert pilot.competition_number == "77"


def test_update_settings_preserves_legacy_admin_username_without_email() -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin User", role="admin", password_hash="hash", profile_type="driver")
    session.add(admin)
    session.commit()

    response = update_settings(
        AccountSettingsUpdate(
            username="admin",
            full_name="Admin User",
            profile_type="driver",
            email=None,
        ),
        admin,
        session,
    )

    session.refresh(admin)
    assert response.username == "admin"
    assert admin.username == "admin"


def test_mesh_device_auto_registration_creates_tracking_inventory() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    response = register_mesh_device(MeshDeviceRegister(mesh_device_id="!ABCDEF12"), user, session)

    session.refresh(user)
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!abcdef12"))
    assert response["mesh_device_id"] == "!abcdef12"
    assert user.mesh_device_id == "!abcdef12"
    assert device is not None
    assert device.owner_user_id == user.id
    assert device.purpose == "tracking"


def test_mesh_device_registration_normalizes_bare_hex_node_id() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    response = register_mesh_device(MeshDeviceRegister(mesh_device_id="435A8B00"), user, session)

    session.refresh(user)
    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!435a8b00"))
    assert response["mesh_device_id"] == "!435a8b00"
    assert user.mesh_device_id == "!435a8b00"
    assert device is not None


def test_nontracking_mesh_device_does_not_replace_tracking_mirror() -> None:
    session = _session()
    user = User(username="driver@example.com", full_name="Driver User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    register_mesh_device(MeshDeviceRegister(mesh_device_id="!tracker"), user, session)
    create_mesh_device(
        MeshDeviceCreate(device_id="!driverwifi", label="Driver Gateway", purpose="driver_wifi"),
        user,
        session,
    )

    session.refresh(user)
    driver_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!driverwifi"))
    assert user.mesh_device_id == "!tracker"
    assert driver_device is not None
    assert driver_device.purpose == "driver_wifi"


def test_mesh_device_update_can_rename_tracking_device_and_mirror() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add(user)
    session.commit()

    register_mesh_device(MeshDeviceRegister(mesh_device_id="!tracker"), user, session)

    response = update_mesh_device(
        "!tracker",
        MeshDeviceUpdate(device_id="!NEWTRACK", label="Primary tracker", purpose="tracking"),
        user,
        session,
    )

    session.refresh(user)
    old_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    new_device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!newtrack"))
    assert response.device_id == "!newtrack"
    assert user.mesh_device_id == "!newtrack"
    assert old_device is None
    assert new_device is not None
    assert new_device.label == "Primary tracker"
    assert new_device.purpose == "tracking"


def test_mesh_device_update_rejects_duplicate_device_id() -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner User", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other User", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.commit()

    create_mesh_device(MeshDeviceCreate(device_id="!mine", label="Mine", purpose="driver_mesh"), owner, session)
    create_mesh_device(MeshDeviceCreate(device_id="!taken", label="Taken", purpose="driver_mesh"), other, session)

    try:
        update_mesh_device("!mine", MeshDeviceUpdate(device_id="!taken"), owner, session)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    else:
        raise AssertionError("Expected duplicate device ID update to be rejected")


def test_admin_user_payload_includes_owned_mesh_devices() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tracker")
    session.add_all([admin, user])
    session.flush()
    session.add_all(
        [
            MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"),
            MeshDevice(owner_user_id=user.id, device_id="!relay", label="Relay", purpose="relay"),
        ]
    )
    session.commit()

    response = list_users(admin, session)
    pilot_payload = next(item for item in response if item.id == user.id)

    assert pilot_payload.mesh_device_id == "!tracker"
    assert [device.device_id for device in pilot_payload.mesh_devices] == ["!relay", "!tracker"]
    assert {device.device_id: device.is_pilot_tracker for device in pilot_payload.mesh_devices} == {
        "!relay": False,
        "!tracker": True,
    }


def test_settings_mesh_device_update_is_reflected_in_admin_user_payload() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tahoe")
    session.add_all([admin, user])
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!tahoe", label="Tahoe Supreme", purpose="tracking"))
    session.commit()

    update_mesh_device(
        "!tahoe",
        MeshDeviceUpdate(device_id="!tahoe", label="Tahoe Supreme", purpose="driver_wifi"),
        user,
        session,
    )

    settings_device = list_mesh_devices(user, session)[0]
    admin_payload = next(item for item in list_users(admin, session) if item.id == user.id)
    admin_device = admin_payload.mesh_devices[0]

    assert settings_device.id == admin_device.id
    assert settings_device.device_id == admin_device.device_id == "!tahoe"
    assert settings_device.label == admin_device.label == "Tahoe Supreme"
    assert settings_device.purpose == admin_device.purpose == "driver_wifi"
    assert settings_device.is_pilot_tracker is False
    assert admin_device.is_pilot_tracker is False
    assert admin_payload.mesh_device_id is None


def test_admin_can_select_switch_and_clear_user_pilot_tracker() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id="!tracker")
    session.add_all([admin, user])
    session.flush()
    session.add_all(
        [
            MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"),
            MeshDevice(owner_user_id=user.id, device_id="!backup", label="Backup", purpose="relay"),
        ]
    )
    session.commit()

    selected = admin_set_user_tracking_mesh_device(
        user.id,
        MeshDeviceRegister(mesh_device_id="!backup"),
        admin,
        session,
    )

    session.refresh(user)
    old_tracker = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!tracker"))
    backup = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!backup"))
    assert selected.mesh_device_id == "!backup"
    assert user.mesh_device_id == "!backup"
    assert old_tracker is not None and old_tracker.purpose == "tracking"
    assert backup is not None and backup.purpose == "tracking"
    assert {device.device_id: device.is_pilot_tracker for device in selected.mesh_devices} == {
        "!backup": True,
        "!tracker": False,
    }

    cleared = admin_set_user_tracking_mesh_device(
        user.id,
        MeshDeviceRegister(mesh_device_id=None),
        admin,
        session,
    )

    session.refresh(user)
    session.refresh(backup)
    assert cleared.mesh_device_id is None
    assert user.mesh_device_id is None
    assert {device.device_id: device.is_pilot_tracker for device in cleared.mesh_devices} == {
        "!backup": False,
        "!tracker": False,
    }


def test_admin_can_edit_user_mesh_device_fields() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash")
    session.add_all([admin, user])
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!relay", label="Relay", purpose="relay"))
    session.commit()

    response = admin_update_user_mesh_device(
        user.id,
        "!relay",
        MeshDeviceUpdate(device_id="!newrelay", label="Roof Relay", purpose="base_station"),
        admin,
        session,
    )

    device = session.scalar(select(MeshDevice).where(MeshDevice.device_id == "!newrelay"))
    assert device is not None
    assert device.label == "Roof Relay"
    assert device.purpose == "base_station"
    assert response.mesh_devices[0].device_id == "!newrelay"
    assert response.mesh_devices[0].is_pilot_tracker is False


def test_unselected_tracking_mesh_device_does_not_resolve_as_pilot_assignment() -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot User", role="pilot", password_hash="hash", mesh_device_id=None)
    session.add(user)
    session.flush()
    session.add(MeshDevice(owner_user_id=user.id, device_id="!tracker", label="Tracker", purpose="tracking"))
    session.commit()

    resolved_user, resolved_device = resolve_mesh_device_assignment(session, "!tracker")

    assert resolved_user is None
    assert resolved_device is not None
    assert resolved_device.device_id == "!tracker"


def test_change_password_requires_current_password() -> None:
    session = _session()
    user = User(username="admin", full_name="Admin User", role="admin", password_hash="old-hash")
    session.add(user)
    session.commit()

    with patch("app.routers.auth.verify_password", return_value=False):
        try:
            change_password(PasswordChangeRequest(current_password="wrong", new_password="new-secret-1"), user, session)
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 401
        else:
            raise AssertionError("Expected password change to reject an invalid current password")


def test_admin_can_update_user_role_and_profile_type() -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin User", role="admin", profile_type="pilot", password_hash="hash")
    previous_profile_type_updated_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)
    target = User(
        username="pilot@example.com",
        full_name="Pilot User",
        role="pilot",
        profile_type="pilot",
        password_hash="hash",
        profile_type_updated_at=previous_profile_type_updated_at,
    )
    session.add_all([admin, target])
    session.commit()

    response = update_user_account(
        target.id,
        AdminUserUpdate(role="organizer", profile_type="driver", is_active=True),
        admin,
        session,
    )

    session.refresh(target)
    assert response.role == "organizer"
    assert target.role == "organizer"
    assert target.profile_type == "driver"
    assert _utc(target.profile_type_updated_at) > previous_profile_type_updated_at
    assert _utc(response.profile_type_updated_at) > previous_profile_type_updated_at
