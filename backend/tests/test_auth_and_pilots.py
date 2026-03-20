from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventPilot, Pilot, User
from app.routers.auth import change_password, register, update_settings, update_user_account
from app.routers.pilots import assign_existing_pilot
from app.schemas import AccountSettingsUpdate, AdminUserUpdate, PasswordChangeRequest, RegisterRequest


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_register_links_existing_pilot_by_email() -> None:
    session = _session()
    pilot = Pilot(first_name="Casey", last_name="Flyer", email="casey@example.com", competition_number="42")
    session.add(pilot)
    session.commit()

    with patch("app.routers.auth.hash_password", return_value="hashed-password"):
        response = register(
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


def test_update_settings_updates_pilot_profile_and_username() -> None:
    session = _session()
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com", nation="US")
    user = User(username="robin@example.com", full_name="Robin Wing", role="pilot", password_hash="hash", pilot_id=None)
    session.add_all([pilot, user])
    session.commit()
    user.pilot_id = pilot.id
    session.commit()

    response = update_settings(
        AccountSettingsUpdate(
            username="robin.wing",
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
    assert response.username == "robin.wing"
    assert response.profile_type == "driver"
    assert user.username == "robin.wing"
    assert user.profile_type == "driver"
    assert pilot.email == "pilot@example.com"
    assert pilot.nation == "USA"
    assert pilot.competition_number == "77"


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
