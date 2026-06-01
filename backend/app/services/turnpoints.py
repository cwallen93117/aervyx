from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from app.models import Turnpoint, TurnpointSource


CANONICAL_SYMBOLS = {"grass_strip", "paved_runway", "dot", "bar"}
CORE_FIELD_KEYS = {"name", "code", "latitude", "longitude", "elevation_m", "symbol"}
SUPPORTED_FORMATS = {".csv": "csv", ".geojson": "geojson", ".json": "geojson", ".gpx": "gpx"}


@dataclass
class TurnpointRecord:
    name: str
    code: str | None
    latitude: float
    longitude: float
    elevation_m: float | None
    symbol: str | None = None
    extra_json: dict = field(default_factory=dict)
    source_row_index: int | None = None


@dataclass
class TurnpointParseResult:
    file_format: str
    records: list[TurnpointRecord]
    schema_json: dict = field(default_factory=dict)


def validate_coordinate(latitude: float, longitude: float) -> None:
    if not -90 <= latitude <= 90:
        raise ValueError(f"Latitude out of range: {latitude}")
    if not -180 <= longitude <= 180:
        raise ValueError(f"Longitude out of range: {longitude}")


def detect_format(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_FORMATS:
        raise ValueError("Unsupported turnpoint format. Use CSV, GPX, or GeoJSON.")
    return SUPPORTED_FORMATS[extension]


def normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    symbol = str(value).strip()
    if not symbol:
        return None
    lowered = symbol.lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "grass": "grass_strip",
        "grass_strip": "grass_strip",
        "green_airplane": "grass_strip",
        "green_plane": "grass_strip",
        "paved": "paved_runway",
        "paved_runway": "paved_runway",
        "black_airplane": "paved_runway",
        "black_plane": "paved_runway",
        "runway": "paved_runway",
        "dot": "dot",
        "standard_dot": "dot",
        "bar": "bar",
        "cocktail": "bar",
        "cocktail_glass": "bar",
    }
    normalized = aliases.get(lowered, lowered)
    return normalized if normalized in CANONICAL_SYMBOLS else None


def parse_turnpoint_upload(filename: str, content: bytes) -> TurnpointParseResult:
    file_format = detect_format(filename)
    if file_format == "csv":
        records, schema = parse_csv_turnpoints_with_schema(content.decode("utf-8-sig"))
    elif file_format == "gpx":
        records, schema = parse_gpx_turnpoints_with_schema(content.decode("utf-8"))
    else:
        records, schema = parse_geojson_turnpoints_with_schema(content.decode("utf-8"))
    return TurnpointParseResult(file_format=file_format, records=records, schema_json=schema)


def _first_present(row: dict, candidates: Iterable[str]) -> tuple[str | None, str | None]:
    lower_map = {str(key).lower(): key for key in row.keys() if key is not None}
    for candidate in candidates:
        key = lower_map.get(candidate.lower())
        if key is not None:
            value = row.get(key)
            return key, None if value is None else str(value)
    return None, None


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def parse_csv_turnpoints_with_schema(text: str) -> tuple[list[TurnpointRecord], dict]:
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = list(reader.fieldnames or [])
    records: list[TurnpointRecord] = []
    field_map: dict[str, str] = {}
    for index, row in enumerate(reader):
        name_key, name = _first_present(row, ["name", "Name"])
        code_key, code = _first_present(row, ["code", "Code"])
        lat_key, latitude_text = _first_present(row, ["latitude", "Latitude", "lat"])
        lon_key, longitude_text = _first_present(row, ["longitude", "Longitude", "lon", "lng"])
        ele_key, elevation_text = _first_present(row, ["elevation_m", "ElevationM", "elevation", "alt", "altitude"])
        symbol_key, symbol_text = _first_present(row, ["symbol", "sym", "icon"])
        if not name or latitude_text is None or longitude_text is None:
            raise ValueError("CSV must include name, latitude, and longitude columns.")
        latitude = float(latitude_text)
        longitude = float(longitude_text)
        validate_coordinate(latitude, longitude)
        field_map.update({key: value for key, value in {
            "name": name_key,
            "code": code_key,
            "latitude": lat_key,
            "longitude": lon_key,
            "elevation_m": ele_key,
            "symbol": symbol_key,
        }.items() if value})
        core_columns = {value for value in field_map.values() if value}
        extra = {key: value for key, value in row.items() if key not in core_columns and value not in (None, "")}
        records.append(
            TurnpointRecord(
                name=name.strip(),
                code=code.strip() if code and code.strip() else None,
                latitude=latitude,
                longitude=longitude,
                elevation_m=_float_or_none(elevation_text),
                symbol=normalize_symbol(symbol_text),
                extra_json=extra,
                source_row_index=index,
            )
        )
    if not records:
        raise ValueError("No turnpoints found in upload.")
    schema = {"columns": fieldnames, "field_map": field_map}
    return records, schema


def parse_csv_turnpoints(text: str) -> list[TurnpointRecord]:
    records, _schema = parse_csv_turnpoints_with_schema(text)
    return records


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _child_text(element: ET.Element, *names: str) -> str | None:
    wanted = {name.lower() for name in names}
    for child in element:
        if _local_name(child.tag).lower() in wanted and child.text:
            text = child.text.strip()
            if text:
                return text
    return None


def _normalize_code(value: str | None) -> str | None:
    if value is None:
        return None
    code = value.strip()
    if not code:
        return None
    parsed = urlparse(code)
    if parsed.scheme and parsed.netloc:
        return None
    if len(code) > 40:
        return code[:40]
    return code


def parse_gpx_turnpoints_with_schema(text: str) -> tuple[list[TurnpointRecord], dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("Invalid GPX upload.") from exc

    records: list[TurnpointRecord] = []
    point_index = 1
    extra_keys: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag).lower() not in {"wpt", "rtept"}:
            continue
        latitude = float(element.attrib["lat"])
        longitude = float(element.attrib["lon"])
        validate_coordinate(latitude, longitude)
        name = _child_text(element, "name", "desc") or f"Turnpoint {point_index}"
        sym_text = _child_text(element, "sym")
        code = _normalize_code(_child_text(element, "type", "cmt")) or _normalize_code(sym_text)
        symbol = normalize_symbol(sym_text)
        elevation_text = _child_text(element, "ele")
        extra: dict[str, str] = {}
        for child in element:
            key = _local_name(child.tag)
            if key.lower() in {"name", "desc", "type", "cmt", "sym", "ele"}:
                continue
            if child.text and child.text.strip() and len(child) == 0:
                extra[key] = child.text.strip()
                extra_keys.add(key)
        records.append(TurnpointRecord(name=name, code=code, latitude=latitude, longitude=longitude, elevation_m=_float_or_none(elevation_text), symbol=symbol, extra_json=extra, source_row_index=point_index - 1))
        point_index += 1
    if not records:
        raise ValueError("No waypoint records found in GPX upload.")
    return records, {"extra_keys": sorted(extra_keys)}


def parse_gpx_turnpoints(text: str) -> list[TurnpointRecord]:
    records, _schema = parse_gpx_turnpoints_with_schema(text)
    return records


def parse_geojson_turnpoints_with_schema(text: str) -> tuple[list[TurnpointRecord], dict]:
    payload = json.loads(text)
    if payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON upload must be a FeatureCollection.")
    records: list[TurnpointRecord] = []
    property_keys: list[str] = []
    for index, feature in enumerate(payload.get("features", [])):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        if geometry.get("type") != "Point":
            continue
        for key in properties.keys():
            if key not in property_keys:
                property_keys.append(key)
        longitude, latitude, *rest = geometry.get("coordinates", [])
        validate_coordinate(latitude, longitude)
        elevation_m = float(rest[0]) if rest else None
        name = str(properties.get("name") or properties.get("Name") or "Turnpoint").strip()
        code = properties.get("code") or properties.get("Code")
        symbol = normalize_symbol(properties.get("symbol") or properties.get("sym") or properties.get("icon"))
        core_property_keys = {"name", "Name", "code", "Code", "symbol", "sym", "icon"}
        extra = {key: value for key, value in properties.items() if key not in core_property_keys}
        records.append(TurnpointRecord(name=name, code=str(code).strip() if code not in (None, "") else None, latitude=latitude, longitude=longitude, elevation_m=elevation_m, symbol=symbol, extra_json=extra, source_row_index=index))
    if not records:
        raise ValueError("No point features found in GeoJSON upload.")
    return records, {"property_keys": property_keys}


def parse_geojson_turnpoints(text: str) -> list[TurnpointRecord]:
    records, _schema = parse_geojson_turnpoints_with_schema(text)
    return records


def _turnpoint_to_record(turnpoint: Turnpoint) -> TurnpointRecord:
    return TurnpointRecord(
        name=turnpoint.name,
        code=turnpoint.code,
        latitude=turnpoint.latitude,
        longitude=turnpoint.longitude,
        elevation_m=turnpoint.elevation_m,
        symbol=normalize_symbol(turnpoint.symbol),
        extra_json=turnpoint.extra_json or {},
        source_row_index=turnpoint.source_row_index,
    )


def serialize_turnpoints(source: TurnpointSource, turnpoints: list[Turnpoint]) -> bytes:
    records = [_turnpoint_to_record(turnpoint) for turnpoint in sorted(turnpoints, key=lambda item: (item.source_row_index is None, item.source_row_index or 0, item.id))]
    schema = source.schema_json or {}
    if source.file_format == "csv":
        return serialize_csv_turnpoints(records, schema).encode("utf-8")
    if source.file_format == "gpx":
        return serialize_gpx_turnpoints(records, schema).encode("utf-8")
    return serialize_geojson_turnpoints(records, schema).encode("utf-8")


def serialize_csv_turnpoints(records: list[TurnpointRecord], schema: dict) -> str:
    field_map = dict(schema.get("field_map") or {})
    columns = list(schema.get("columns") or [])
    defaults = {
        "name": "name",
        "code": "code",
        "latitude": "latitude",
        "longitude": "longitude",
        "elevation_m": "elevation_m",
        "symbol": "symbol",
    }
    for key, default_column in defaults.items():
        if not field_map.get(key):
            field_map[key] = default_column
        if field_map[key] not in columns:
            columns.append(field_map[key])
    for record in records:
        for key in (record.extra_json or {}).keys():
            if key not in columns:
                columns.append(key)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for record in records:
        row = {key: "" for key in columns}
        row.update(record.extra_json or {})
        row[field_map["name"]] = record.name
        row[field_map["code"]] = record.code or ""
        row[field_map["latitude"]] = f"{record.latitude:.8f}".rstrip("0").rstrip(".")
        row[field_map["longitude"]] = f"{record.longitude:.8f}".rstrip("0").rstrip(".")
        row[field_map["elevation_m"]] = "" if record.elevation_m is None else f"{record.elevation_m:.2f}".rstrip("0").rstrip(".")
        row[field_map["symbol"]] = record.symbol or ""
        writer.writerow(row)
    return output.getvalue()


def serialize_geojson_turnpoints(records: list[TurnpointRecord], schema: dict) -> str:
    property_keys = list(schema.get("property_keys") or [])
    for key in ["name", "code", "symbol"]:
        if key not in property_keys:
            property_keys.append(key)
    features = []
    for record in records:
        properties = dict(record.extra_json or {})
        properties["name"] = record.name
        if record.code:
            properties["code"] = record.code
        if record.symbol:
            properties["symbol"] = record.symbol
        ordered_properties = {key: properties[key] for key in property_keys if key in properties}
        for key, value in properties.items():
            if key not in ordered_properties:
                ordered_properties[key] = value
        coordinates: list[float] = [record.longitude, record.latitude]
        if record.elevation_m is not None:
            coordinates.append(record.elevation_m)
        features.append({"type": "Feature", "properties": ordered_properties, "geometry": {"type": "Point", "coordinates": coordinates}})
    return json.dumps({"type": "FeatureCollection", "features": features}, indent=2) + "\n"


def serialize_gpx_turnpoints(records: list[TurnpointRecord], schema: dict) -> str:
    root = ET.Element("gpx", {"version": "1.1", "creator": "Aervyx"})
    extra_keys = list(schema.get("extra_keys") or [])
    for record in records:
        wpt = ET.SubElement(root, "wpt", {"lat": f"{record.latitude:.8f}".rstrip("0").rstrip("."), "lon": f"{record.longitude:.8f}".rstrip("0").rstrip(".")})
        ET.SubElement(wpt, "name").text = record.name
        if record.elevation_m is not None:
            ET.SubElement(wpt, "ele").text = f"{record.elevation_m:.2f}".rstrip("0").rstrip(".")
        if record.code:
            ET.SubElement(wpt, "type").text = record.code
        if record.symbol:
            ET.SubElement(wpt, "sym").text = record.symbol
        extras = record.extra_json or {}
        for key in extra_keys:
            if key in extras and extras[key] not in (None, ""):
                ET.SubElement(wpt, key).text = str(extras[key])
        for key, value in extras.items():
            if key not in extra_keys and value not in (None, ""):
                ET.SubElement(wpt, key).text = str(value)
    ET.indent(root, space="  ")
    return "<?xml version='1.0' encoding='UTF-8'?>\n" + ET.tostring(root, encoding="unicode") + "\n"


def rewrite_turnpoint_source_file(source: TurnpointSource, turnpoints: list[Turnpoint]) -> str:
    content = serialize_turnpoints(source, turnpoints)
    stored_path = Path(source.stored_path)
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{stored_path.name}.", dir=str(stored_path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        os.replace(temp_name, stored_path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    sha256 = hashlib.sha256(content).hexdigest()
    source.sha256 = sha256
    return sha256
