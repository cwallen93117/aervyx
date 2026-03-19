from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AirspaceRecord:
    name: str
    class_code: str | None
    type_code: str | None
    display_category: str
    lower_limit_label: str | None
    upper_limit_label: str | None
    lower_limit_m: float | None
    upper_limit_m: float | None
    geometry_json: dict
    label_latitude: float | None
    label_longitude: float | None
    is_restricted_field: bool


SUPPORTED_AIRSPACE_FORMATS = {
    ".txt": "openair",
    ".openair": "openair",
    ".air": "openair",
    ".geojson": "geojson",
    ".json": "geojson",
}

AIRSPACE_FILTER_OPTIONS = ["B", "C", "D", "P", "Q", "R", "TFR", "OTHER"]


def detect_airspace_format(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_AIRSPACE_FORMATS:
        raise ValueError("Unsupported airspace format. Use OpenAir (.txt/.openair/.air) or GeoJSON.")
    return SUPPORTED_AIRSPACE_FORMATS[extension]


def parse_airspace_upload(filename: str, content: bytes, *, kind: str) -> tuple[str, list[AirspaceRecord]]:
    file_format = detect_airspace_format(filename)
    if file_format == "openair":
        return file_format, parse_openair(content.decode("utf-8-sig", errors="replace"), kind=kind)
    return file_format, parse_geojson_airspaces(content.decode("utf-8"), kind=kind)


def parse_geojson_airspaces(text: str, *, kind: str) -> list[AirspaceRecord]:
    payload = json.loads(text)
    if payload.get("type") != "FeatureCollection":
        raise ValueError("GeoJSON airspace upload must be a FeatureCollection.")
    records: list[AirspaceRecord] = []
    for feature in payload.get("features", []):
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        if geometry_type not in {"Polygon", "MultiPolygon"}:
            continue
        properties = feature.get("properties") or {}
        name = str(properties.get("name") or properties.get("title") or properties.get("Name") or "Airspace").strip()
        class_code = _clean_code(properties.get("class") or properties.get("icaoClass") or properties.get("class_code"))
        type_code = _clean_code(properties.get("type") or properties.get("category") or properties.get("type_code"))
        lower_label = _string_or_none(properties.get("lower") or properties.get("lower_limit"))
        upper_label = _string_or_none(properties.get("upper") or properties.get("upper_limit"))
        lower_limit_m = _parse_altitude(lower_label)
        upper_limit_m = _parse_altitude(upper_label)
        geometry_json = _normalize_geojson_geometry(geometry)
        label_latitude, label_longitude = _geometry_label_point(geometry_json)
        records.append(
            AirspaceRecord(
                name=name,
                class_code=class_code,
                type_code=type_code,
                display_category=_display_category(kind=kind, name=name, class_code=class_code, type_code=type_code),
                lower_limit_label=lower_label,
                upper_limit_label=upper_label,
                lower_limit_m=lower_limit_m,
                upper_limit_m=upper_limit_m,
                geometry_json=geometry_json,
                label_latitude=label_latitude,
                label_longitude=label_longitude,
                is_restricted_field=kind == "restricted_field",
            )
        )
    if not records:
        raise ValueError("No polygon airspace features found in GeoJSON upload.")
    return records


def parse_openair(text: str, *, kind: str) -> list[AirspaceRecord]:
    records: list[AirspaceRecord] = []
    current: _OpenAirBlock | None = None
    center: tuple[float, float] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        if "*" in line:
            line = line.split("*", 1)[0].strip()
        if not line:
            continue

        keyword, _, remainder = line.partition(" ")
        keyword = keyword.upper()
        remainder = remainder.strip()

        if keyword == "AC":
            if current and current.has_geometry:
                records.append(current.to_record(kind=kind))
            current = _OpenAirBlock(class_code=_clean_code(remainder))
            center = None
            continue

        if current is None:
            continue

        if keyword == "AN":
            current.name = remainder or current.name
        elif keyword == "AY":
            current.type_code = _clean_code(remainder)
        elif keyword == "AL":
            current.lower_limit_label = remainder or None
            current.lower_limit_m = _parse_altitude(remainder)
        elif keyword == "AH":
            current.upper_limit_label = remainder or None
            current.upper_limit_m = _parse_altitude(remainder)
        elif keyword == "V" and remainder.upper().startswith("X="):
            center = _parse_coordinate_pair(remainder[2:].strip())
        elif keyword == "DP":
            current.points.append(_point_feature_coord(_parse_coordinate_pair(remainder)))
        elif keyword == "DC":
            if center is None:
                raise ValueError("OpenAir circle command DC requires a V X= center before it.")
            radius_m = _parse_radius_m(remainder)
            current.add_ring(_circle_ring(center, radius_m))
        elif keyword == "DA":
            if center is None:
                raise ValueError("OpenAir arc command DA requires a V X= center before it.")
            bearings = [segment.strip() for segment in remainder.split(",") if segment.strip()]
            if len(bearings) >= 2:
                radius_m = _infer_radius_from_points(current.points, center)
                if radius_m is None and len(bearings) >= 3:
                    radius_m = _parse_radius_m(bearings[2])
                if radius_m is None:
                    raise ValueError("OpenAir DA arc requires an existing radius or explicit radius.")
                current.extend_points(_arc_ring(center, float(bearings[0]), float(bearings[1]), radius_m))
        elif keyword == "DB":
            if center is None:
                raise ValueError("OpenAir arc command DB requires a V X= center before it.")
            parts = [segment.strip() for segment in remainder.split(",") if segment.strip()]
            if len(parts) >= 2:
                start = _parse_coordinate_pair(parts[0])
                end = _parse_coordinate_pair(parts[1])
                current.extend_points(_arc_between_points(center, start, end))

    if current and current.has_geometry:
        records.append(current.to_record(kind=kind))
    if not records:
        raise ValueError("No airspace geometry found in OpenAir upload.")
    return records


@dataclass
class _OpenAirBlock:
    class_code: str | None
    name: str = "Airspace"
    type_code: str | None = None
    lower_limit_label: str | None = None
    upper_limit_label: str | None = None
    lower_limit_m: float | None = None
    upper_limit_m: float | None = None
    points: list[list[float]] = field(default_factory=list)
    rings: list[list[list[float]]] = field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        return bool(self.points or self.rings)

    def extend_points(self, points: list[list[float]]) -> None:
        self.points.extend(points)

    def add_ring(self, ring: list[list[float]]) -> None:
        self.rings.append(ring)

    def to_record(self, *, kind: str) -> AirspaceRecord:
        rings = [*_rings_from_points(self.points), *self.rings]
        geometry_json = {"type": "Polygon", "coordinates": rings}
        label_latitude, label_longitude = _geometry_label_point(geometry_json)
        return AirspaceRecord(
            name=self.name,
            class_code=self.class_code,
            type_code=self.type_code,
            display_category=_display_category(kind=kind, name=self.name, class_code=self.class_code, type_code=self.type_code),
            lower_limit_label=self.lower_limit_label,
            upper_limit_label=self.upper_limit_label,
            lower_limit_m=self.lower_limit_m,
            upper_limit_m=self.upper_limit_m,
            geometry_json=geometry_json,
            label_latitude=label_latitude,
            label_longitude=label_longitude,
            is_restricted_field=kind == "restricted_field",
        )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_code(value: object) -> str | None:
    text = _string_or_none(value)
    return text.upper() if text else None


def _display_category(*, kind: str, name: str | None, class_code: str | None, type_code: str | None) -> str:
    if kind == "restricted_field":
        return "RESTRICTED_FIELD"
    upper_name = (name or "").upper()
    upper_class = (class_code or "").upper()
    upper_type = (type_code or "").upper()
    if "TFR" in upper_name or upper_class == "TFR" or upper_type == "TFR":
        return "TFR"
    for code in (upper_class, upper_type):
        if code in {"B", "C", "D", "P", "Q", "R"}:
            return code
    return "OTHER"


def _rings_from_points(points: list[list[float]]) -> list[list[list[float]]]:
    if not points:
        return []
    ring = points.copy()
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return [ring]


def _normalize_geojson_geometry(geometry: dict) -> dict:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates", [])
    if geometry_type == "Polygon":
        return {"type": "Polygon", "coordinates": coordinates}
    if geometry_type == "MultiPolygon":
        first_polygon = coordinates[0] if coordinates else []
        return {"type": "Polygon", "coordinates": first_polygon}
    raise ValueError("Unsupported GeoJSON geometry type.")


def _geometry_label_point(geometry_json: dict) -> tuple[float | None, float | None]:
    coordinates = geometry_json.get("coordinates") or []
    if not coordinates:
        return None, None
    ring = coordinates[0]
    if not ring:
        return None, None
    lons = [point[0] for point in ring]
    lats = [point[1] for point in ring]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _parse_radius_m(text: str) -> float:
    raw = text.strip().upper()
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        raise ValueError(f"Could not parse OpenAir radius: {text}")
    value = float(match.group(0))
    if "NM" in raw:
        return value * 1852
    if "KM" in raw:
        return value * 1000
    if "M" in raw:
        return value
    return value * 1852


def _parse_altitude(text: str | None) -> float | None:
    if not text:
        return None
    raw = text.strip().upper()
    if raw in {"SFC", "GND", "GROUND"}:
        return 0.0
    if raw.startswith("FL"):
        try:
            return float(raw[2:]) * 100 * 0.3048
        except ValueError:
            return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        return None
    value = float(match.group(0))
    if "FT" in raw or "F" in raw:
        return value * 0.3048
    if "M" in raw:
        return value
    return value


def _parse_coordinate_pair(text: str) -> tuple[float, float]:
    cleaned = " ".join(text.replace(",", " ").split())
    decimal_match = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*([NS])\s+([+-]?\d+(?:\.\d+)?)\s*([EW])$", cleaned, flags=re.IGNORECASE)
    if decimal_match:
        latitude = float(decimal_match.group(1))
        if decimal_match.group(2).upper() == "S":
            latitude *= -1
        longitude = float(decimal_match.group(3))
        if decimal_match.group(4).upper() == "W":
            longitude *= -1
        return latitude, longitude

    pair_match = re.findall(r"([0-9:+.\-]+)\s*([NSEW])", cleaned, flags=re.IGNORECASE)
    if len(pair_match) >= 2:
        latitude = _parse_single_coordinate(pair_match[0][0], pair_match[0][1].upper())
        longitude = _parse_single_coordinate(pair_match[1][0], pair_match[1][1].upper())
        return latitude, longitude
    raise ValueError(f"Could not parse OpenAir coordinate pair: {text}")


def _parse_single_coordinate(value: str, hemisphere: str) -> float:
    raw = value.strip().replace(" ", "")
    if ":" in raw:
        pieces = [float(piece) for piece in raw.split(":") if piece]
        degrees = pieces[0]
        minutes = pieces[1] if len(pieces) > 1 else 0.0
        seconds = pieces[2] if len(pieces) > 2 else 0.0
        decimal = degrees + (minutes / 60) + (seconds / 3600)
    else:
        try:
            numeric = float(raw)
        except ValueError as exc:
            raise ValueError(f"Could not parse coordinate component: {value}") from exc
        whole_digits = raw.split(".", 1)[0]
        degree_digits = 2 if hemisphere in {"N", "S"} else 3
        if len(whole_digits.replace("-", "")) > degree_digits:
            normalized = whole_digits.replace("-", "")
            degrees = float(normalized[:degree_digits])
            minutes = float(normalized[degree_digits:] + (("." + raw.split(".", 1)[1]) if "." in raw else ""))
            decimal = degrees + (minutes / 60)
        else:
            decimal = numeric
    if hemisphere in {"S", "W"}:
        decimal *= -1
    return decimal


def _point_feature_coord(point: tuple[float, float]) -> list[float]:
    latitude, longitude = point
    return [longitude, latitude]


def _circle_ring(center: tuple[float, float], radius_m: float, steps: int = 48) -> list[list[float]]:
    latitude, longitude = center
    ring: list[list[float]] = []
    for step in range(steps + 1):
        bearing = (360 / steps) * step
        ring.append(_destination_point(latitude, longitude, radius_m, bearing))
    return ring


def _infer_radius_from_points(points: list[list[float]], center: tuple[float, float]) -> float | None:
    if not points:
        return None
    return _distance_m(center[0], center[1], points[-1][1], points[-1][0])


def _arc_ring(center: tuple[float, float], start_bearing: float, end_bearing: float, radius_m: float, steps: int = 32) -> list[list[float]]:
    if end_bearing < start_bearing:
        end_bearing += 360
    span = end_bearing - start_bearing
    return [
        _destination_point(center[0], center[1], radius_m, start_bearing + (span * step / steps))
        for step in range(steps + 1)
    ]


def _arc_between_points(center: tuple[float, float], start: tuple[float, float], end: tuple[float, float], steps: int = 32) -> list[list[float]]:
    radius_m = _distance_m(center[0], center[1], start[0], start[1])
    start_bearing = _bearing(center[0], center[1], start[0], start[1])
    end_bearing = _bearing(center[0], center[1], end[0], end[1])
    return _arc_ring(center, start_bearing, end_bearing, radius_m, steps=steps)


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_m = 6371000
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(delta_lon / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    y = math.sin(delta_lon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(delta_lon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def _destination_point(latitude: float, longitude: float, distance_m: float, bearing_deg: float) -> list[float]:
    earth_radius_m = 6371000
    bearing = math.radians(bearing_deg)
    lat1 = math.radians(latitude)
    lon1 = math.radians(longitude)
    angular_distance = distance_m / earth_radius_m
    lat2 = math.asin(math.sin(lat1) * math.cos(angular_distance) + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing))
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return [math.degrees(lon2), math.degrees(lat2)]
