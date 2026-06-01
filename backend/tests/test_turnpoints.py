from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, Turnpoint, TurnpointSource, User
from app.routers.turnpoints import create_source_turnpoint, update_turnpoint
from app.schemas import TurnpointWrite
from app.services.turnpoints import parse_csv_turnpoints, parse_csv_turnpoints_with_schema, parse_geojson_turnpoints, parse_gpx_turnpoints, serialize_csv_turnpoints


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
