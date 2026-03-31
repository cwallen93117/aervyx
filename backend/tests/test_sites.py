from datetime import date, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_session
from app.deps import require_admin
from app.models import FlightSite, Pilot, PilotFlight, PilotFlightTrackPoint, SiteSettings, User
from app.routers.sites import router
from app.services.logbook import rescan_unmatched_flights_for_sites


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _pilot(session: Session, *, email: str) -> Pilot:
    pilot = Pilot(first_name=email.split("@", 1)[0], last_name="Pilot", email=email)
    session.add(pilot)
    session.flush()
    return pilot


def _site(
    session: Session,
    *,
    name: str,
    latitude: float,
    longitude: float,
    is_active: bool = True,
    flight_count: int = 0,
) -> FlightSite:
    site = FlightSite(
        name=name,
        city_state="",
        latitude=latitude,
        longitude=longitude,
        is_active=is_active,
        flight_count=flight_count,
    )
    session.add(site)
    session.flush()
    return site


def _flight(
    session: Session,
    *,
    pilot: Pilot,
    source_kind: str = "app_upload",
    flight_date: date = date(2026, 3, 28),
    site_id: int | None = None,
    site_name: str = "",
    points: list[tuple[float, float]] | None = None,
) -> PilotFlight:
    flight = PilotFlight(
        pilot_id=pilot.id,
        source_kind=source_kind,
        event_id=None,
        task_id=None,
        site_id=site_id,
        igc_upload_id=None,
        flight_date=flight_date,
        site_name=site_name,
        notes=None,
        duration_seconds=None,
        highest_altitude_m=None,
        best_climb_mps=None,
        filename=None,
        sha256=None,
        stored_path=None,
        metadata_json={},
    )
    session.add(flight)
    session.flush()

    if points:
        start = datetime(2026, 3, 28, 12, 0, 0)
        for sequence, (latitude, longitude) in enumerate(points):
            session.add(
                PilotFlightTrackPoint(
                    flight_id=flight.id,
                    sequence=sequence,
                    recorded_at=start + timedelta(seconds=sequence),
                    latitude=latitude,
                    longitude=longitude,
                    pressure_altitude_m=None,
                    gps_altitude_m=None,
                )
            )

    session.flush()
    return flight


def test_rescan_matches_unassigned_track_backed_flight() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=1000))
    pilot = _pilot(session, email="pilot1@example.com")
    site = _site(session, name="Ridge Launch", latitude=35.0, longitude=-82.0)
    flight = _flight(session, pilot=pilot, points=[(35.0003, -82.0)])
    session.commit()

    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(flight)
    session.refresh(site)

    assert result.scanned_count == 1
    assert result.matched_count == 1
    assert result.unmatched_count == 0
    assert flight.site_id == site.id
    assert flight.site_name == "Ridge Launch"
    assert site.flight_count == 1


def test_rescan_reassigns_existing_wrong_site_for_all_users() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=1000))
    pilot_one = _pilot(session, email="pilot1@example.com")
    pilot_two = _pilot(session, email="pilot2@example.com")
    correct_site = _site(session, name="Correct", latitude=35.0, longitude=-82.0)
    wrong_site = _site(session, name="Wrong", latitude=36.0, longitude=-83.0, flight_count=4)
    first_flight = _flight(
        session,
        pilot=pilot_one,
        site_id=wrong_site.id,
        site_name="Wrong",
        points=[(35.0002, -82.0)],
    )
    second_flight = _flight(session, pilot=pilot_two, points=[(35.0004, -82.0)])
    session.commit()

    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(first_flight)
    session.refresh(second_flight)
    session.refresh(correct_site)
    session.refresh(wrong_site)

    assert result.scanned_count == 2
    assert result.matched_count == 2
    assert result.unmatched_count == 0
    assert first_flight.site_id == correct_site.id
    assert first_flight.site_name == "Correct"
    assert second_flight.site_id == correct_site.id
    assert correct_site.flight_count == 2
    assert wrong_site.flight_count == 0


def test_rescan_skips_manual_flights_and_flights_without_points() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=1000))
    pilot = _pilot(session, email="pilot1@example.com")
    site = _site(session, name="Ridge Launch", latitude=35.0, longitude=-82.0)
    _flight(session, pilot=pilot, source_kind="manual", points=[(35.0, -82.0)])
    _flight(session, pilot=pilot, source_kind="app_upload", points=None)
    session.commit()

    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(site)

    assert result.scanned_count == 0
    assert result.matched_count == 0
    assert result.unmatched_count == 0
    assert site.flight_count == 0


def test_rescan_chooses_nearest_active_site() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=1000))
    pilot = _pilot(session, email="pilot1@example.com")
    _site(session, name="Inactive Exact", latitude=35.0, longitude=-82.0, is_active=False)
    farther_active = _site(session, name="Farther Active", latitude=35.0005, longitude=-82.0)
    nearer_active = _site(session, name="Nearer Active", latitude=35.0002, longitude=-82.0)
    flight = _flight(session, pilot=pilot, points=[(35.0, -82.0)])
    session.commit()

    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(flight)
    session.refresh(farther_active)
    session.refresh(nearer_active)

    assert result.scanned_count == 1
    assert result.matched_count == 1
    assert flight.site_id == nearer_active.id
    assert flight.site_name == "Nearer Active"
    assert nearer_active.flight_count == 1
    assert farther_active.flight_count == 0


def test_rescan_keeps_existing_site_when_no_saved_site_matches() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=500))
    pilot = _pilot(session, email="pilot1@example.com")
    original_site = _site(session, name="Original", latitude=34.0, longitude=-81.0)
    _site(session, name="Other Site", latitude=35.0, longitude=-82.0)
    flight = _flight(
        session,
        pilot=pilot,
        site_id=original_site.id,
        site_name="Original",
        points=[(36.0, -83.0)],
    )
    session.commit()

    result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(flight)
    session.refresh(original_site)

    assert result.scanned_count == 1
    assert result.matched_count == 0
    assert result.unmatched_count == 1
    assert flight.site_id == original_site.id
    assert flight.site_name == "Original"
    assert original_site.flight_count == 1


def test_rescan_repeat_does_not_inflate_site_counts() -> None:
    session = _session()
    session.add(SiteSettings(id=1, site_match_radius_m=1000))
    pilot = _pilot(session, email="pilot1@example.com")
    site = _site(session, name="Ridge Launch", latitude=35.0, longitude=-82.0)
    _flight(session, pilot=pilot, points=[(35.0003, -82.0)])
    session.commit()

    first_result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(site)
    first_count = site.flight_count

    second_result = rescan_unmatched_flights_for_sites(session)
    session.commit()
    session.refresh(site)

    assert first_result.matched_count == 1
    assert second_result.matched_count == 1
    assert first_count == 1
    assert site.flight_count == 1


def test_rescan_flights_endpoint_returns_counts() -> None:
    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)

    seed_session = TestingSessionLocal()
    try:
        seed_session.add(SiteSettings(id=1, site_match_radius_m=1000))
        pilot = _pilot(seed_session, email="pilot1@example.com")
        _site(seed_session, name="Ridge Launch", latitude=35.0, longitude=-82.0)
        _flight(seed_session, pilot=pilot, points=[(35.0003, -82.0)])
        _flight(seed_session, pilot=pilot, points=[(37.0, -84.0)])
        seed_session.commit()
    finally:
        seed_session.close()

    test_app = FastAPI()
    test_app.include_router(router)

    def override_session():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_admin() -> User:
        return User(username="admin@example.com", full_name="Admin User", role="admin", password_hash="hash")

    test_app.dependency_overrides[get_session] = override_session
    test_app.dependency_overrides[require_admin] = override_admin

    client = TestClient(test_app)
    response = client.post("/api/admin/sites/rescan-flights")

    assert response.status_code == 200
    assert response.json() == {
        "scanned_count": 2,
        "matched_count": 1,
        "unmatched_count": 1,
    }
