from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Pilot, PilotFlight, PilotFlightTrackPoint, User
from app.routers.logbook import get_flight_track
from app.services.igc import TrackFix
from app.services.logbook import derive_flight_stats, recompute_track_backed_flight_stats


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _fix(
    seconds: int,
    *,
    pressure_altitude_m: int | None,
    gps_altitude_m: int | None,
    latitude: float = 35.0,
    longitude: float = -82.0,
) -> TrackFix:
    return TrackFix(
        recorded_at=datetime(2026, 3, 29, 12, 0, 0) + timedelta(seconds=seconds),
        latitude=latitude,
        longitude=longitude,
        pressure_altitude_m=pressure_altitude_m,
        gps_altitude_m=gps_altitude_m,
    )


def _flight(session: Session) -> PilotFlight:
    pilot = Pilot(first_name="Robin", last_name="Wing", email="robin@example.com")
    session.add(pilot)
    session.flush()
    flight = PilotFlight(
        pilot_id=pilot.id,
        source_kind="app_upload",
        event_id=None,
        task_id=None,
        site_id=None,
        igc_upload_id=None,
        flight_date=date(2026, 3, 29),
        site_name="",
        notes=None,
        duration_seconds=None,
        highest_altitude_m=None,
        best_climb_mps=None,
        filename="flight.igc",
        sha256="abc123",
        stored_path="C:/tmp/flight.igc",
        metadata_json={"pilot_name": "Robin Wing"},
    )
    session.add(flight)
    session.flush()
    return flight


def _add_track_points(
    session: Session,
    flight: PilotFlight,
    points: list[TrackFix],
) -> None:
    for sequence, point in enumerate(points, start=1):
        session.add(
            PilotFlightTrackPoint(
                flight_id=flight.id,
                sequence=sequence,
                recorded_at=point.recorded_at,
                latitude=point.latitude,
                longitude=point.longitude,
                pressure_altitude_m=point.pressure_altitude_m,
                gps_altitude_m=point.gps_altitude_m,
            )
        )
    session.flush()


def test_derive_flight_stats_prefers_pressure_altitude_for_all_altitude_stats() -> None:
    points = [
        _fix(0, pressure_altitude_m=1000, gps_altitude_m=1000),
        _fix(10, pressure_altitude_m=1010, gps_altitude_m=1600),
        _fix(20, pressure_altitude_m=1020, gps_altitude_m=1610),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 1.0
    assert stats.highest_altitude_m == 1020
    assert stats.launch_altitude_m == 1000
    assert stats.landing_altitude_m == 1020
    assert stats.time_in_thermals_seconds == 20
    assert stats.time_on_glide_seconds == 0


def test_derive_flight_stats_falls_back_to_gps_when_pressure_missing() -> None:
    points = [
        _fix(0, pressure_altitude_m=None, gps_altitude_m=500),
        _fix(10, pressure_altitude_m=None, gps_altitude_m=530),
        _fix(20, pressure_altitude_m=None, gps_altitude_m=550),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 3.0
    assert stats.highest_altitude_m == 550
    assert stats.launch_altitude_m == 500
    assert stats.landing_altitude_m == 550
    assert stats.time_in_thermals_seconds == 20
    assert stats.time_on_glide_seconds == 0


def test_derive_flight_stats_ignores_gps_spike_when_pressure_is_stable() -> None:
    points = [
        _fix(0, pressure_altitude_m=2172, gps_altitude_m=1847),
        _fix(2, pressure_altitude_m=2174, gps_altitude_m=2098),
        _fix(4, pressure_altitude_m=2177, gps_altitude_m=2101),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 1.5
    assert stats.highest_altitude_m == 2177


def test_derive_flight_stats_does_not_mix_pressure_and_gps_within_one_flight() -> None:
    points = [
        _fix(0, pressure_altitude_m=100, gps_altitude_m=100),
        _fix(1, pressure_altitude_m=109, gps_altitude_m=109),
        _fix(2, pressure_altitude_m=3, gps_altitude_m=114),
        _fix(3, pressure_altitude_m=None, gps_altitude_m=113),
        _fix(4, pressure_altitude_m=13, gps_altitude_m=114),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 9.0


def test_derive_flight_stats_filters_pressure_altitude_spikes() -> None:
    points = [
        _fix(0, pressure_altitude_m=1000, gps_altitude_m=1000),
        _fix(10, pressure_altitude_m=1080, gps_altitude_m=1080),
        _fix(11, pressure_altitude_m=1180, gps_altitude_m=1180),
        _fix(21, pressure_altitude_m=1090, gps_altitude_m=1090),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 8.0


def test_derive_flight_stats_filters_gps_altitude_spikes_when_gps_is_fallback() -> None:
    points = [
        _fix(0, pressure_altitude_m=None, gps_altitude_m=500),
        _fix(10, pressure_altitude_m=None, gps_altitude_m=580),
        _fix(11, pressure_altitude_m=None, gps_altitude_m=680),
        _fix(21, pressure_altitude_m=None, gps_altitude_m=590),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 8.0


def test_derive_flight_stats_thermal_glide_split_uses_pressure_first_source() -> None:
    points = [
        _fix(0, pressure_altitude_m=1000, gps_altitude_m=1000),
        _fix(10, pressure_altitude_m=1010, gps_altitude_m=1500),
        _fix(20, pressure_altitude_m=1008, gps_altitude_m=1600),
    ]

    stats = derive_flight_stats(points)

    assert stats.best_climb_mps == 1.0
    assert stats.time_in_thermals_seconds == 0
    assert stats.time_on_glide_seconds == 20


def test_recompute_track_backed_flight_stats_updates_stored_summary_and_metadata() -> None:
    session = _session()
    flight = _flight(session)
    points = [
        _fix(0, pressure_altitude_m=1000, gps_altitude_m=1000),
        _fix(10, pressure_altitude_m=1015, gps_altitude_m=1700),
        _fix(20, pressure_altitude_m=1030, gps_altitude_m=1710),
    ]
    _add_track_points(session, flight, points)
    session.commit()

    updated = recompute_track_backed_flight_stats(session, flight)
    session.commit()
    session.refresh(flight)

    assert updated is True
    assert flight.duration_seconds == 20
    assert flight.highest_altitude_m == 1030
    assert flight.best_climb_mps == 1.5
    assert flight.metadata_json["stats"]["launch_altitude_m"] == 1000
    assert flight.metadata_json["stats"]["landing_altitude_m"] == 1030


def test_recompute_track_backed_flight_stats_returns_false_without_track_points() -> None:
    session = _session()
    flight = _flight(session)
    session.commit()

    updated = recompute_track_backed_flight_stats(session, flight)

    assert updated is False


def test_get_flight_track_marks_igc_solid() -> None:
    session = _session()
    flight = _flight(session)
    user = User(username="robin@example.com", full_name="Robin Wing", role="pilot", pilot_id=flight.pilot_id)
    session.add(user)
    _add_track_points(session, flight, [
        _fix(0, pressure_altitude_m=1000, gps_altitude_m=1000),
        _fix(10, pressure_altitude_m=1010, gps_altitude_m=1010, latitude=35.1, longitude=-82.1),
    ])
    session.commit()

    payload = get_flight_track(flight.id, user=user, session=session)

    properties = payload["features"][0]["properties"]
    assert properties["line_style"] == "solid"
    assert properties["track_kind"] == "igc"
