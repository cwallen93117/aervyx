from datetime import date
from io import BytesIO
from pathlib import Path
import zipfile

import pytest
import app.routers.turnpoints as turnpoint_router
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.core.config import get_settings
from app.models import Event, EventTurnpointSlot, Task, TaskPoint, Turnpoint, TurnpointSource, User
from app.routers.turnpoints import (
    create_library_turnpoint,
    delete_library_source,
    deselect_event_turnpoint_source,
    download_event_turnpoint_source,
    list_source_turnpoints,
    list_turnpoint_sources,
    merge_library_sources,
    save_library_source_as,
    select_event_turnpoint_source,
    update_library_source,
    update_library_turnpoint,
)
from app.schemas import TurnpointSourceMerge, TurnpointSourceSaveAs, TurnpointSourceUpdate, TurnpointWrite
from app.services.turnpoints import TurnpointRecord, normalize_symbol, parse_csv_turnpoints, parse_csv_turnpoints_with_schema, parse_geojson_turnpoints, parse_gpx_turnpoints, serialize_csv_turnpoints, serialize_turnpoint_records


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


def test_export_formats_for_downloads() -> None:
    records = [TurnpointRecord(name="Launch", code="LCH", latitude=36.6, longitude=-118.1, elevation_m=1200, symbol="launch")]

    assert b"Launch,LCH,36.6,-118.1,1200,launch" in serialize_turnpoint_records(records, "csv", {})
    assert b"<wpt lat=\"36.6\" lon=\"-118.1\">" in serialize_turnpoint_records(records, "gpx", {})
    assert b"name,code,country,lat,lon,elev,style" in serialize_turnpoint_records(records, "cup", {})
    assert b"G  WGS 84\nU  1\nW  LCH A 36.6N 118.1W" in serialize_turnpoint_records(records, "wpt", {})
    kmz = serialize_turnpoint_records(records, "kmz", {})
    with zipfile.ZipFile(BytesIO(kmz)) as archive:
        assert "doc.kml" in archive.namelist()
        assert b"<name>Launch</name>" in archive.read("doc.kml")


def _library_source(session: Session, tmp_path: Path, filename: str, points: list[dict]) -> TurnpointSource:
    stored_path = tmp_path / filename
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_text("name,latitude,longitude\n", encoding="utf-8")
    source = TurnpointSource(
        event_id=None,
        filename=filename,
        file_format=Path(filename).suffix.lstrip(".") or "csv",
        sha256=f"hash-{filename}",
        stored_path=str(stored_path),
        schema_json={},
        enabled=True,
    )
    session.add(source)
    session.flush()
    for index, values in enumerate(points):
        session.add(Turnpoint(event_id=None, source_id=source.id, source_row_index=index, **values))
    session.commit()
    return source


def test_update_library_turnpoint_rewrites_source_file(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(session, tmp_path, "turnpoints.csv", [{"name": "Old", "latitude": 36, "longitude": -118, "extra_json": {"notes": "old note"}}])
    point = session.query(Turnpoint).filter(Turnpoint.source_id == source.id).one()

    payload = TurnpointWrite(name="New", code="N", symbol="bar", latitude=36.5, longitude=-118.5, elevation_m=1200, extra_json={"notes": "saved"})
    updated = update_library_turnpoint(source.id, point.id, payload, admin, session)

    assert updated.symbol == "bar"
    assert "New" in Path(source.stored_path).read_text(encoding="utf-8")
    assert session.get(TurnpointSource, source.id).sha256 != f"hash-{source.filename}"


def test_create_library_turnpoint_has_no_owning_event(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(session, tmp_path, "turnpoints.csv", [])

    created = create_library_turnpoint(source.id, TurnpointWrite(name="New", latitude=1, longitude=2), admin, session)

    assert created.event_id is None
    assert session.get(Turnpoint, created.id).event_id is None


def test_rename_library_source_corrects_extension(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(session, tmp_path, "old.csv", [{"name": "A", "latitude": 1, "longitude": 2}])

    updated = update_library_source(source.id, TurnpointSourceUpdate(filename="new-name.gpx"), admin, session)

    assert updated.filename == "new-name.csv"
    assert session.get(TurnpointSource, source.id).filename == "new-name.csv"


@pytest.mark.parametrize("source_format", ["csv", "gpx", "geojson"])
@pytest.mark.parametrize("output_format", ["csv", "gpx", "cup", "wpt", "kmz"])
def test_save_as_converts_every_supported_format_and_preserves_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_format: str,
    output_format: str,
) -> None:
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    get_settings.cache_clear()
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(
        session,
        tmp_path,
        f"original.{source_format}",
        [{"name": "A", "code": "A1", "latitude": 1, "longitude": 2, "elevation_m": 3, "symbol": "bar", "extra_json": {"notes": "kept"}}],
    )
    original_bytes = Path(source.stored_path).read_bytes()

    saved = save_library_source_as(source.id, TurnpointSourceSaveAs(filename="copy.wrong", file_format=output_format), admin, session)
    cloned = session.get(TurnpointSource, saved.id)
    cloned_points = session.query(Turnpoint).filter(Turnpoint.source_id == saved.id).all()

    assert saved.filename == f"copy.{output_format}"
    assert cloned is not None
    assert cloned.event_id is None
    assert Path(cloned.stored_path).exists()
    assert len(cloned_points) == 1
    assert cloned_points[0].symbol == "bar"
    assert cloned_points[0].extra_json == {"notes": "kept"}
    assert Path(source.stored_path).read_bytes() == original_bytes
    assert session.query(EventTurnpointSlot).filter(EventTurnpointSlot.source_id == saved.id).count() == 0
    get_settings.cache_clear()


def test_save_as_defaults_to_current_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    get_settings.cache_clear()
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(session, tmp_path, "original.geojson", [{"name": "A", "latitude": 1, "longitude": 2}])

    saved = save_library_source_as(source.id, TurnpointSourceSaveAs(filename="copy.csv"), admin, session)

    assert saved.file_format == "geojson"
    assert saved.filename == "copy.geojson"
    get_settings.cache_clear()


def test_merge_is_ordered_and_collapses_only_exact_duplicates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    get_settings.cache_clear()
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    first = _library_source(session, tmp_path / "first", "first.csv", [
        {"name": " Alpha ", "code": "A", "latitude": 1.0000004, "longitude": 2.0000004, "extra_json": {"winner": "first"}},
        {"name": "Bravo", "code": "B", "latitude": 3, "longitude": 4},
    ])
    second = _library_source(session, tmp_path / "second", "second.geojson", [
        {"name": "alpha", "code": " a ", "latitude": 1.00000049, "longitude": 2.00000049, "extra_json": {"winner": "second"}},
        {"name": "Charlie", "code": "C", "latitude": 5, "longitude": 6},
    ])

    merged = merge_library_sources(TurnpointSourceMerge(source_ids=[second.id, first.id], filename="combined.csv"), admin, session)
    points = session.query(Turnpoint).filter(Turnpoint.source_id == merged.id).order_by(Turnpoint.source_row_index).all()

    assert merged.filename == "combined.gpx"
    assert merged.file_format == "gpx"
    assert [point.name for point in points] == ["alpha", "Charlie", "Bravo"]
    assert points[0].extra_json == {"winner": "second"}
    assert session.query(Turnpoint).filter(Turnpoint.source_id.in_([first.id, second.id])).count() == 4
    get_settings.cache_clear()


def test_merge_requires_two_distinct_sources(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    source = _library_source(session, tmp_path, "one.csv", [{"name": "A", "latitude": 1, "longitude": 2}])

    with pytest.raises(HTTPException) as exc:
        merge_library_sources(TurnpointSourceMerge(source_ids=[source.id, source.id], filename="bad"), admin, session)

    assert exc.value.status_code == 400


@pytest.mark.parametrize("operation", ["save-as", "merge"])
def test_new_library_file_operations_are_atomic_on_audit_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    monkeypatch.setenv("UPLOAD_ROOT", str(tmp_path))
    get_settings.cache_clear()
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    session.add(admin)
    session.commit()
    first = _library_source(session, tmp_path / "originals", "first.csv", [{"name": "A", "latitude": 1, "longitude": 2}])
    second = _library_source(session, tmp_path / "originals", "second.csv", [{"name": "B", "latitude": 3, "longitude": 4}])
    original_source_count = session.query(TurnpointSource).count()
    original_point_count = session.query(Turnpoint).count()

    def fail_audit(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(turnpoint_router, "log_action", fail_audit)
    with pytest.raises(RuntimeError, match="audit unavailable"):
        if operation == "save-as":
            save_library_source_as(first.id, TurnpointSourceSaveAs(filename="copy", file_format="gpx"), admin, session)
        else:
            merge_library_sources(TurnpointSourceMerge(source_ids=[first.id, second.id], filename="merged"), admin, session)

    assert session.query(TurnpointSource).count() == original_source_count
    assert session.query(Turnpoint).count() == original_point_count
    assert not (tmp_path / "turnpoints").exists() or not any((tmp_path / "turnpoints").iterdir())
    get_settings.cache_clear()


def test_events_share_library_sources_and_pilots_read_selected_files(tmp_path: Path) -> None:
    session = _session()
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    first_event = Event(name="First", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    second_event = Event(name="Second", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    session.add_all([pilot, admin, first_event, second_event])
    session.commit()
    source = _library_source(session, tmp_path, "shared.csv", [{"name": "A", "latitude": 1, "longitude": 2}])

    select_event_turnpoint_source(first_event.id, source.id, admin, session)
    select_event_turnpoint_source(second_event.id, source.id, admin, session)

    assert [item.id for item in list_turnpoint_sources(first_event.id, pilot, session)] == [source.id]
    assert [item.id for item in list_turnpoint_sources(second_event.id, pilot, session)] == [source.id]
    assert [item.name for item in list_source_turnpoints(first_event.id, source.id, pilot, session)] == ["A"]
    deselect_event_turnpoint_source(first_event.id, source.id, admin, session)
    assert list_turnpoint_sources(first_event.id, pilot, session) == []
    assert [item.id for item in list_turnpoint_sources(second_event.id, pilot, session)] == [source.id]


def test_pilot_can_download_selected_event_waypoint_file(tmp_path: Path) -> None:
    session = _session()
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Meet", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    session.add_all([pilot, admin, event])
    session.commit()
    source = _library_source(session, tmp_path, "shared.csv", [{"name": "A", "code": "A1", "latitude": 1, "longitude": 2}])
    select_event_turnpoint_source(event.id, source.id, admin, session)

    response = download_event_turnpoint_source(event.id, source.id, "cup", pilot, session)

    assert response.media_type == "text/csv"
    assert b"name,code,country,lat,lon,elev,style" in response.body


def test_event_waypoint_download_rejects_unsupported_export_format(tmp_path: Path) -> None:
    session = _session()
    pilot = User(username="pilot@example.com", full_name="Pilot", role="pilot", password_hash="hash")
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="Meet", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC", visibility="public")
    session.add_all([pilot, admin, event])
    session.commit()
    source = _library_source(session, tmp_path, "shared.csv", [{"name": "A", "latitude": 1, "longitude": 2}])
    select_event_turnpoint_source(event.id, source.id, admin, session)

    with pytest.raises(HTTPException) as exc:
        download_event_turnpoint_source(event.id, source.id, "geojson", pilot, session)

    assert exc.value.status_code == 400


def test_library_delete_preserves_task_point_snapshot(tmp_path: Path) -> None:
    session = _session()
    admin = User(username="admin", full_name="Admin", role="admin", password_hash="hash")
    event = Event(name="History", location="", starts_on=date(2026, 5, 1), ends_on=date(2026, 5, 1), timezone="UTC")
    session.add_all([admin, event])
    session.flush()
    task = Task(event_id=event.id, name="Task 1")
    session.add(task)
    session.commit()
    source = _library_source(session, tmp_path, "history.csv", [{"name": "Snapshot", "latitude": 1, "longitude": 2}])
    point = session.query(Turnpoint).filter(Turnpoint.source_id == source.id).one()
    task_point = TaskPoint(task_id=task.id, position=1, point_type="turnpoint", turnpoint_id=point.id, name="Snapshot", latitude=1, longitude=2)
    session.add(task_point)
    session.commit()

    delete_library_source(source.id, admin, session)

    preserved = session.get(TaskPoint, task_point.id)
    assert preserved is not None
    assert preserved.turnpoint_id is None
    assert (preserved.name, preserved.latitude, preserved.longitude) == ("Snapshot", 1, 2)
