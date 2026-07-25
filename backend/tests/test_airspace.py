from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import AirspaceSource, Event, User
from app.routers.airspace import download_airspace_source
from app.services.airspace import parse_geojson_airspaces, parse_openair


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_parse_openair_polygon_restricted_fields() -> None:
    payload = """AC DZ
AN DO NOT LAND - Sample Field
AL SFC
AH SFC
DP 29.07850074121879 N 82.0368666704882 W
DP 29.08041844762213 N 82.02447092495572 W
DP 29.09966082403472 N 82.02456480175168 W
DP 29.07850074121879 N 82.0368666704882 W
"""
    records = parse_openair(payload, kind="restricted_field")
    assert len(records) == 1
    assert records[0].is_restricted_field is True
    assert records[0].display_category == "RESTRICTED_FIELD"
    assert records[0].name == "DO NOT LAND - Sample Field"
    assert records[0].geometry_json["type"] == "Polygon"


def test_parse_openair_circle_airspace() -> None:
    payload = """AC C
AN Test Class C
AL SFC
AH FL100
V X=28.5000 N 81.5000 W
DC 5 NM
"""
    records = parse_openair(payload, kind="airspace")
    assert len(records) == 1
    assert records[0].display_category == "C"
    assert records[0].upper_limit_m is not None
    assert len(records[0].geometry_json["coordinates"][0]) > 10


def test_parse_geojson_airspace_polygons() -> None:
    payload = """{
      "type": "FeatureCollection",
      "features": [
        {
          "type": "Feature",
          "properties": {
            "name": "Restricted Area",
            "class": "R",
            "lower_limit": "SFC",
            "upper_limit": "4500 ft"
          },
          "geometry": {
            "type": "Polygon",
            "coordinates": [[[-81.9, 28.3], [-81.8, 28.3], [-81.8, 28.4], [-81.9, 28.3]]]
          }
        }
      ]
    }"""
    records = parse_geojson_airspaces(payload, kind="airspace")
    assert len(records) == 1
    assert records[0].display_category == "R"
    assert records[0].lower_limit_m == 0


def test_parse_openair_tfr_from_name() -> None:
    payload = """AC R
AN TFR - Presidential Movement
AL SFC
AH FL180
DP 28.9000 N 81.5000 W
DP 28.9500 N 81.4500 W
DP 29.0000 N 81.5000 W
DP 28.9000 N 81.5000 W
"""
    records = parse_openair(payload, kind="airspace")
    assert len(records) == 1
    assert records[0].display_category == "TFR"


def test_download_airspace_source_returns_stored_file(tmp_path: Path) -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    event = Event(name="Meet", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    session.add_all([user, event])
    session.flush()
    path = tmp_path / "airspace.openair"
    path.write_text("AC R\nAN Test\n", encoding="utf-8")
    source = AirspaceSource(event_id=event.id, kind="airspace", filename="airspace.openair", file_format="openair", sha256="hash", stored_path=str(path), enabled=True)
    session.add(source)
    session.commit()

    response = download_airspace_source(event.id, source.id, user, session)

    assert Path(response.path) == path
    assert response.media_type == "text/plain"


def test_download_airspace_source_respects_event_visibility(tmp_path: Path) -> None:
    session = _session()
    user = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    event = Event(name="Meet", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="private")
    session.add_all([user, event])
    session.flush()
    path = tmp_path / "airspace.openair"
    path.write_text("AC R\nAN Test\n", encoding="utf-8")
    source = AirspaceSource(event_id=event.id, kind="airspace", filename="airspace.openair", file_format="openair", sha256="hash", stored_path=str(path), enabled=True)
    session.add(source)
    session.commit()

    with pytest.raises(HTTPException) as exc:
        download_airspace_source(event.id, source.id, user, session)

    assert exc.value.status_code == 404
