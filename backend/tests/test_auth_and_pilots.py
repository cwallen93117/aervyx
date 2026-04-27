from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request

from app.db import Base
from app.models import Event, EventPilot, MeshDevice, Pilot, User
from app.routers.auth import change_password, create_mesh_device, register, register_mesh_device, update_mesh_device, update_settings, update_user_account
from app.routers.pilots import assign_existing_pilot
from app.schemas import AccountSettingsUpdate, AdminUserUpdate, MeshDeviceCreate, MeshDeviceRegister, MeshDeviceUpdate, PasswordChangeRequest, RegisterRequest


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


def test_update_settings_updates_pilot_profile_and_username_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com", nation="US")
    user = User(username="robin@example.com", full_name="Robin Wing", role="pilot", password_hash="hash", pilot_id=None)
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
    assert user.username == "pilot@example.com"
    assert user.profile_type == "driver"
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
    target = User(username="pilot@example.com", full_name="Pilot User", role="pilot", profile_type="pilot", password_hash="hash")
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
