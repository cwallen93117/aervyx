from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.core.config import get_settings
from app.models import Event, EventPilot, Pilot, Turnpoint, TurnpointSource, User
from app.routers.auth import list_waypoint_files, update_challenge_settings
from app.routers.turnpoints import create_source_turnpoint, save_turnpoint_source_as, update_turnpoint, update_turnpoint_source
from app.schemas import ChallengeSettingsUpdate, TurnpointSourceSaveAs, TurnpointSourceUpdate, TurnpointWrite
from app.services.turnpoints import normalize_symbol, parse_csv_turnpoints, parse_csv_turnpoints_with_schema, parse_geojson_turnpoints, parse_gpx_turnpoints, serialize_csv_turnpoints


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_parse_csv_turnpoints() -> None:
    records = parse_csv_turnpoints("name,code,latitude,longitude\nLaunch,LCH,36.6,-118.0\n")
    assert len(records) == 1
    assert records[0].code == "LCH"


def test_parse_and_serialize_csv_preserves_symbol_and_extra_columns() -> None:
    records, schema = parse_csv_turnpoints_with_schema("name,lat,lon,sym,notes\nGrass,36.6,-118.0,Grass Strip,landable\n")
    assert records[0].symbol == "grass_strip"
    assert records[0].extra_json == {"notes": "landable"}

    csv_text = serialize_csv_turnpoints(records, schema)
    assert "name,lat,lon,sym,notes" in csv_text
    assert "Grass,36.6,-118,grass_strip,landable" in csv_text


def test_lz_and_launch_symbols_are_supported() -> None:
    assert normalize_symbol("LZ") == "lz"
    assert normalize_symbol("Landing Zone") == "lz"
    assert normalize_symbol("Launch") == "launch"
    assert normalize_symbol("takeoff") == "launch"


def test_parse_geojson_turnpoints() -> None:
    payload = '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"name":"Goal"},"geometry":{"type":"Point","coordinates":[-118.3,36.8]}}]}'
    records = parse_geojson_turnpoints(payload)
    assert records[0].name == "Goal"


def test_parse_gpx_turnpoints() -> None:
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="FlightComp">
  <wpt lat="36.606" lon="-118.062">
    <name>Launch Ridge</name>
    <sym>LCH</sym>
    <ele>1900</ele>
  </wpt>
  <wpt lat="36.810" lon="-118.320">
    <name>Goal Field</name>
    <type>GL1</type>
  </wpt>
</gpx>
"""
    records = parse_gpx_turnpoints(payload)
    assert len(records) == 2
    assert records[0].name == "Launch Ridge"
    assert records[0].code == "LCH"
    assert records[0].elevation_m == 1900
    assert records[1].code == "GL1"


def test_parse_gpx_ignores_url_symbol_codes() -> None:
    payload = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="FlightComp">
  <wpt lat="38.692468708" lon="-75.071779914">
    <ele>2.5</ele>
    <name>dewey</name>
    <sym>http://maps.google.com/mapfiles/kml/shapes/flag.png</sym>
  </wpt>
</gpx>
"""
    records = parse_gpx_turnpoints(payload)
    assert len(records) == 1
    assert records[0].name == "dewey"
    assert records[0].code is None


def test_update_turnpoint_rewrites_source_file(tmp_path: Path) -> None:
    session = _session()
    event = Event(name="Waypoint Edit", location="Hills", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    stored_path = tmp_path / "turnpoints.csv"
    stored_path.write_text("name,lat,lon,symbol,notes\nOld,36,-118,,old note\n", encoding="utf-8")
    session.add_all([event, admin])
    session.flush()
    source = TurnpointSource(event_id=event.id, filename="turnpoints.csv", file_format="csv", sha256="old", stored_path=str(stored_path), schema_json={"columns": ["name", "code", "lat", "lon", "symbol", "notes"], "field_map": {"name": "name", "code": "code", "latitude": "lat", "longitude": "lon", "symbol": "symbol"}})
    session.add(source)
    session.flush()
    point = Turnpoint(event_id=event.id, source_id=source.id, name="Old", latitude=36, longitude=-118, source_row_index=0, extra_json={"notes": "old note"})
    session.add(point)
    session.commit()

    payload = TurnpointWrite(name="New", code="N", symbol="bar", latitude=36.5, longitude=-118.5, elevation_m=1200, extra_json={"notes": "saved"})
    updated = update_turnpoint(event.id, point.id, payload, admin, session)

    assert updated.symbol == "bar"
    assert "New,N,36.5,-118.5,bar,saved" in stored_path.read_text(encoding="utf-8")
    assert session.get(TurnpointSource, source.id).sha256 != "old"


def test_create_turnpoint_rejects_cross_event_source(tmp_path: Path) -> None:
    session = _session()
    event = Event(name="One", location="A", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    other = Event(name="Two", location="B", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    path = tmp_path / "turnpoints.csv"
    path.write_text("name,latitude,longitude\n", encoding="utf-8")
    session.add_all([event, other, admin])
    session.flush()
    source = TurnpointSource(event_id=event.id, filename="turnpoints.csv", file_format="csv", sha256="old", stored_path=str(path), schema_json={})
    session.add(source)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        create_source_turnpoint(other.id, source.id, TurnpointWrite(name="Nope", latitude=1, longitude=1), admin, session)

    assert exc.value.status_code == 404


def test_rename_turnpoint_source_changes_download_filename_metadata(tmp_path: Path) -> None:
    session = _session()
    event = Event(name="Rename", location="Hills", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    path = tmp_path / "old.csv"
    path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
    session.add_all([event, admin])
    session.flush()
    source = TurnpointSource(event_id=event.id, filename="old.csv", file_format="csv", sha256="old", stored_path=str(path), enabled=True)
    session.add(source)
    session.commit()

    updated = update_turnpoint_source(event.id, source.id, TurnpointSourceUpdate(filename="new-name"), admin, session)

    assert updated.filename == "new-name.csv"
    assert session.get(TurnpointSource, source.id).filename == "new-name.csv"


def test_save_turnpoint_source_as_clones_file_and_waypoints(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    get_settings.cache_clear()
    session = _session()
    event = Event(name="Save As", location="Hills", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 3), timezone="UTC")
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    original_path = tmp_path / "original.csv"
    original_path.write_text("name,latitude,longitude,symbol\nA,1,2,bar\n", encoding="utf-8")
    session.add_all([event, admin])
    session.flush()
    source = TurnpointSource(
        event_id=event.id,
        filename="original.csv",
        file_format="csv",
        sha256="old",
        stored_path=str(original_path),
        schema_json={"columns": ["name", "latitude", "longitude", "symbol"], "field_map": {"name": "name", "latitude": "latitude", "longitude": "longitude", "symbol": "symbol"}},
        enabled=True,
    )
    session.add(source)
    session.flush()
    session.add(Turnpoint(event_id=event.id, source_id=source.id, name="A", latitude=1, longitude=2, symbol="bar", source_row_index=0))
    session.commit()

    saved = save_turnpoint_source_as(event.id, source.id, TurnpointSourceSaveAs(filename="copy"), admin, session)
    cloned = session.get(TurnpointSource, saved.id)
    cloned_points = session.query(Turnpoint).filter(Turnpoint.source_id == saved.id).all()

    assert saved.filename == "copy.csv"
    assert cloned is not None
    assert Path(cloned.stored_path).exists()
    assert "A,1,2,bar" in Path(cloned.stored_path).read_text(encoding="utf-8")
    assert len(cloned_points) == 1
    assert cloned_points[0].symbol == "bar"
    get_settings.cache_clear()


def test_waypoint_file_list_includes_owned_and_manageable_sources(tmp_path: Path) -> None:
    session = _session()
    owner_pilot = Pilot(first_name="Owner", last_name="Pilot", email="owner@example.com")
    member_pilot = Pilot(first_name="Member", last_name="Pilot", email="member@example.com")
    session.add_all([owner_pilot, member_pilot])
    session.flush()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", pilot_id=owner_pilot.id, password_hash="hash")
    member = User(username="member@example.com", full_name="Member", role="pilot", pilot_id=member_pilot.id, password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    session.add_all([owner, member, admin])
    session.flush()
    defaults = Event(name="Challenge Defaults", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="challenge_defaults", owner_user_id=owner.id, visibility="private")
    challenge = Event(name="Owner Challenge", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="challenge", owner_user_id=owner.id, visibility="participants")
    official = Event(name="Official Meet", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="competition", visibility="private")
    session.add_all([defaults, challenge, official])
    session.flush()
    session.add(EventPilot(event_id=challenge.id, pilot_id=member_pilot.id))
    for event, filename in ((defaults, "defaults.csv"), (challenge, "challenge.csv"), (official, "official.csv")):
        path = tmp_path / filename
        path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
        source = TurnpointSource(event_id=event.id, filename=filename, file_format="csv", sha256=filename, stored_path=str(path), enabled=True)
        session.add(source)
        session.flush()
        session.add(Turnpoint(event_id=event.id, source_id=source.id, name=filename, latitude=1, longitude=2, source_row_index=0))
    session.commit()

    owner_files = {item.filename: item for item in list_waypoint_files(user=owner, session=session)}
    member_files = {item.filename: item for item in list_waypoint_files(user=member, session=session)}
    admin_files = {item.filename: item for item in list_waypoint_files(user=admin, session=session)}

    assert owner_files["defaults.csv"].can_edit is True
    assert owner_files["challenge.csv"].can_edit is True
    assert "official.csv" not in owner_files
    assert member_files["challenge.csv"].can_edit is False
    assert "defaults.csv" not in member_files
    assert admin_files["official.csv"].can_edit is True
    assert admin_files["challenge.csv"].can_edit is False


def test_non_owner_can_view_but_not_edit_public_challenge_waypoints(tmp_path: Path) -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.flush()
    event = Event(name="Public Challenge", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="challenge", owner_user_id=owner.id, visibility="public")
    session.add(event)
    session.flush()
    path = tmp_path / "public.csv"
    path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
    source = TurnpointSource(event_id=event.id, filename="public.csv", file_format="csv", sha256="old", stored_path=str(path), enabled=True)
    session.add(source)
    session.flush()
    point = Turnpoint(event_id=event.id, source_id=source.id, name="A", latitude=1, longitude=2, source_row_index=0)
    session.add(point)
    session.commit()

    assert "public.csv" in {item.filename for item in list_waypoint_files(user=other, session=session)}
    with pytest.raises(HTTPException) as exc:
        update_turnpoint(event.id, point.id, TurnpointWrite(name="B", latitude=1, longitude=2), other, session)
    assert exc.value.status_code == 403

    updated = update_turnpoint(event.id, point.id, TurnpointWrite(name="Launch", symbol="launch", latitude=1, longitude=2), owner, session)
    assert updated.symbol == "launch"


def test_official_waypoint_writes_still_require_staff(tmp_path: Path) -> None:
    session = _session()
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Official", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="competition", visibility="public")
    session.add_all([pilot, admin, event])
    session.flush()
    path = tmp_path / "official.csv"
    path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
    source = TurnpointSource(event_id=event.id, filename="official.csv", file_format="csv", sha256="old", stored_path=str(path), enabled=True)
    session.add(source)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        update_turnpoint_source(event.id, source.id, TurnpointSourceUpdate(filename="pilot"), pilot, session)
    assert exc.value.status_code == 403

    assert update_turnpoint_source(event.id, source.id, TurnpointSourceUpdate(filename="admin"), admin, session).filename == "admin.csv"


def test_challenge_settings_rejects_inaccessible_waypoint_source(tmp_path: Path) -> None:
    session = _session()
    owner = User(username="owner@example.com", full_name="Owner", role="pilot", password_hash="hash")
    other = User(username="other@example.com", full_name="Other", role="pilot", password_hash="hash")
    session.add_all([owner, other])
    session.flush()
    defaults = Event(name="Challenge Defaults", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", event_kind="challenge_defaults", owner_user_id=owner.id, visibility="private")
    session.add(defaults)
    session.flush()
    path = tmp_path / "defaults.csv"
    path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
    source = TurnpointSource(event_id=defaults.id, filename="defaults.csv", file_format="csv", sha256="old", stored_path=str(path), enabled=True)
    session.add(source)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        update_challenge_settings(ChallengeSettingsUpdate(settings={"turnpoint_source_id": source.id}), user=other, session=session)
    assert exc.value.status_code == 403

    saved = update_challenge_settings(ChallengeSettingsUpdate(settings={"turnpoint_source_id": source.id}), user=owner, session=session)
    assert saved.settings["turnpoint_source_id"] == source.id
