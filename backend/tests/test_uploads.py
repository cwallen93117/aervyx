from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, EventPilot, Pilot
from app.routers.uploads import _match_pilot_for_upload


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_match_pilot_for_upload_uses_header_name() -> None:
    session = _session()
    event = Event(name="Header Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    pilot = Pilot(first_name="Charles", last_name="Allen", email="charles@example.com", competition_number="12")
    session.add_all([event, pilot])
    session.flush()
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "random-track.igc",
        {"pilot_name": "Charles Allen"},
    )

    assert matched is not None
    assert matched.id == pilot.id


def test_match_pilot_for_upload_uses_filename_when_header_missing() -> None:
    session = _session()
    event = Event(name="Filename Match", location="Hills", starts_on=date(2026, 3, 18), ends_on=date(2026, 3, 20), timezone="UTC")
    pilot = Pilot(first_name="Cory", last_name="Barnwell", email="cory@example.com", competition_number="27")
    session.add_all([event, pilot])
    session.flush()
    session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
    session.commit()

    matched = _match_pilot_for_upload(
        session,
        event.id,
        "Cory_Barnwell.1748889288000.7028.igc",
        {},
    )

    assert matched is not None
    assert matched.id == pilot.id

