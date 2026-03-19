from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import EventPilot, Pilot, User

DEFAULT_ADMIN_PASSWORD = "admin1234"
DEFAULT_PILOT_PASSWORD = "pilot1234"


def bootstrap_demo_data(session: Session) -> None:
    admin = session.scalar(select(User).where(User.username == "admin"))
    if admin is None:
        session.add(User(username="admin", full_name="Flight Director", role="admin", password_hash=hash_password(DEFAULT_ADMIN_PASSWORD)))

    demo_pilot = session.scalar(select(User).where(User.username == "pilot-demo"))
    if demo_pilot is None:
        pilot = Pilot(first_name="Demo", last_name="Pilot", email="pilot@example.com", nation="USA", competition_number="101", civl_id="DEMO101")
        session.add(pilot)
        session.flush()
        session.add(User(username="pilot-demo", full_name="Demo Pilot", role="pilot", pilot_id=pilot.id, password_hash=hash_password(DEFAULT_PILOT_PASSWORD)))
