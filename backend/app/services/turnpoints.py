from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TurnpointRecord:
    name: str
    code: str | None
    latitude: float
    longitude: float
    elevation_m: float | None


SUPPORTED_FORMATS = {".csv": "csv", ".geojson": "geojson", ".json": "geojson", ".gpx": "gpx"}


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


def parse_turnpoint_upload(filename: str, content: bytes) -> tuple[str, list[TurnpointRecord]]:
    file_format = detect_format(filename)
    if file_format == "csv":
        return file_format, parse_csv_turnpoints(content.decode("utf-8-sig"))
    if file_format == "gpx":
        return file_format, parse_gpx_turnpoints(content.decode("utf-8"))
    return file_format, parse_geojson_turnpoints(content.decode("utf-8"))


def parse_csv_turnpoints(text: str) -> list[TurnpointRecord]:
    reader = csv.DictReader(io.StringIO(text))
    records: list[TurnpointRecord] = []
    for row in reader:
        name = (row.get("name") or row.get("Name") or "").strip()
        code = (row.get("code") or row.get("Code") or "").strip() or None
        latitude_text = row.get("latitude") or row.get("Latitude") or row.get("lat")
        longitude_text = row.get("longitude") or row.get("Longitude") or row.get("lon") or row.get("lng")
        if not name or latitude_text is None or longitude_text is None:
            raise ValueError("CSV must include name, latitude, and longitude columns.")
        latitude = float(latitude_text)
        longitude = float(longitude_text)
        validate_coordinate(latitude, longitude)
        elevation_text = row.get("elevation_m") or row.get("ElevationM") or row.get("elevation")
        elevation_m = float(elevation_text) if elevation_text not in (None, "") else None
        records.append(TurnpointRecord(name=name, code=code, latitude=latitude, longitude=longitude, elevation_m=elevation_m))
    if not records:
        raise ValueError("No turnpoints found in upload.")
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


def parse_gpx_turnpoints(text: str) -> list[TurnpointRecord]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError("Invalid GPX upload.") from exc

    records: list[TurnpointRecord] = []
    point_index = 1
    for element in root.iter():
        if _local_name(element.tag).lower() not in {"wpt", "rtept"}:
            continue
        latitude = float(element.attrib["lat"])
        longitude = float(element.attrib["lon"])
        validate_coordinate(latitude, longitude)
        name = _child_text(element, "name", "desc") or f"Turnpoint {point_index}"
        code = _child_text(element, "sym", "type", "cmt")
        elevation_text = _child_text(element, "ele")
        elevation_m = float(elevation_text) if elevation_text is not None else None
        records.append(TurnpointRecord(name=name, code=code, latitude=latitude, longitude=longitude, elevation_m=elevation_m))
        point_index += 1
    if not records:
        raise ValueError("No waypoint records found in GPX upload.")
    return records


def parse_geojson_turnpoints(text: str) -> list[TurnpointRecord]:
    payload = json.loads(text)
    if payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON upload must be a FeatureCollection.")
    records: list[TurnpointRecord] = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        if geometry.get("type") != "Point":
            continue
        longitude, latitude, *rest = geometry.get("coordinates", [])
        validate_coordinate(latitude, longitude)
        elevation_m = float(rest[0]) if rest else None
        name = str(properties.get("name") or properties.get("Name") or "Turnpoint").strip()
        code = properties.get("code") or properties.get("Code")
        records.append(TurnpointRecord(name=name, code=code, latitude=latitude, longitude=longitude, elevation_m=elevation_m))
    if not records:
        raise ValueError("No point features found in GeoJSON upload.")
    return records
