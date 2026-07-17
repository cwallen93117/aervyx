from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.core.config import get_settings
from app.models import Event, Turnpoint, TurnpointSource, User
from app.routers.auth import list_waypoint_files
from app.routers.turnpoints import create_source_turnpoint, save_turnpoint_source_as, update_turnpoint, update_turnpoint_source
from app.schemas import TurnpointSourceSaveAs, TurnpointSourceUpdate, TurnpointWrite
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


def test_waypoint_file_list_uses_event_visibility_and_staff_editing(tmp_path: Path) -> None:
    session = _session()
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    public_event = Event(name="Public Event", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    private_event = Event(name="Private Event", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="private")
    session.add_all([pilot, admin, public_event, private_event])
    session.flush()
    sources: dict[str, TurnpointSource] = {}
    for event, filename in ((public_event, "public.csv"), (private_event, "private.csv")):
        path = tmp_path / filename
        path.write_text("name,latitude,longitude\nA,1,2\n", encoding="utf-8")
        source = TurnpointSource(event_id=event.id, filename=filename, file_format="csv", sha256=filename, stored_path=str(path), enabled=True)
        session.add(source)
        sources[filename] = source
    session.commit()

    pilot_files = {item.filename: item for item in list_waypoint_files(user=pilot, session=session)}
    admin_files = {item.filename: item for item in list_waypoint_files(user=admin, session=session)}
    assert set(pilot_files) == {"public.csv"}
    assert pilot_files["public.csv"].can_edit is False
    assert set(admin_files) == {"public.csv", "private.csv"}
    assert all(item.can_edit for item in admin_files.values())

    with pytest.raises(HTTPException) as exc:
        update_turnpoint_source(public_event.id, sources["public.csv"].id, TurnpointSourceUpdate(filename="pilot"), pilot, session)
    assert exc.value.status_code == 403
    assert update_turnpoint_source(public_event.id, sources["public.csv"].id, TurnpointSourceUpdate(filename="admin"), admin, session).filename == "admin.csv"
