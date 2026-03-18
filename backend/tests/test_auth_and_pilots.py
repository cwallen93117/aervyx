from datetime import date
from unittest.mock import patch

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventPilot, Pilot, User
from app.routers.auth import register
from app.routers.pilots import assign_existing_pilot
from app.schemas import RegisterRequest


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
