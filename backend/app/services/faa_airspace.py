"""FAA Airspace data cache — fetch from ArcGIS, store in DB, serve from memory.

Three FAA data sources (all public, no API key):
  - Class_Airspace: controlled airspace (B, C, D, E, Mode-C)
  - Special_Use_Airspace: restricted/prohibited/warning/alert/MOA
  - National_Defense_Airspace_TFR_Areas: defense TFRs

Background tasks check ArcGIS lastEditDate and re-import when stale.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import FaaAirspaceFeature, FaaAirspaceMeta
from app.services.integration_credentials import (
    FaaNotamsCredentials,
    build_faa_notams_query_url,
    get_effective_faa_notams_credentials,
)

logger = logging.getLogger("faa_airspace")

# ---------------------------------------------------------------------------
# ArcGIS endpoint configuration
# ---------------------------------------------------------------------------

_CLASS_BASE = "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Class_Airspace/FeatureServer/0"
_CLASS_FIELDS = "IDENT,NAME,CLASS,LOCAL_TYPE,TYPE_CODE,UPPER_DESC,LOWER_DESC,UPPER_VAL,UPPER_UOM,LOWER_VAL,LOWER_UOM,CITY,STATE"

# Split class airspace into per-class queries to avoid ArcGIS 504 timeouts
_CLASS_QUERIES = [
    "CLASS='B'",
    "CLASS='C'",
    "CLASS='D'",
]

_SOURCES = {
    "class": {
        "base": _CLASS_BASE,
        "fields": _CLASS_FIELDS,
        "where": _CLASS_QUERIES,  # list — fetched as separate queries then merged
    },
    "sua": {
        "base": "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Special_Use_Airspace/FeatureServer/0",
        "fields": "NAME,TYPE_CODE,CLASS,UPPER_DESC,LOWER_DESC,UPPER_VAL,UPPER_UOM,LOWER_VAL,LOWER_UOM,CITY,STATE",
        "where": "1=1",
    },
    "tfr": {
        "base": "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/National_Defense_Airspace_TFR_Areas/FeatureServer/0",
        "fields": "*",
        "where": "1=1",
    },
}

PAGE_SIZE = 1000

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

# List of dicts: {"feature": <GeoJSON Feature dict>, "bbox": (min_lat, max_lat, min_lon, max_lon)}
_feature_cache: list[dict] | None = None
_cache_loaded_at: float = 0.0

# Simplified geometry epsilon (~0.002° ≈ ~200m, good for map display)
_SIMPLIFY_EPSILON = 0.002


def _simplify_ring(ring: list, epsilon: float) -> list:
    """Ramer-Douglas-Peucker line simplification."""
    if len(ring) <= 4:
        return ring

    def _perp_dist(pt, start, end):
        dx, dy = end[0] - start[0], end[1] - start[1]
        len_sq = dx * dx + dy * dy
        if len_sq == 0:
            return ((pt[0] - start[0]) ** 2 + (pt[1] - start[1]) ** 2) ** 0.5
        t = max(0, min(1, ((pt[0] - start[0]) * dx + (pt[1] - start[1]) * dy) / len_sq))
        return ((pt[0] - (start[0] + t * dx)) ** 2 + (pt[1] - (start[1] + t * dy)) ** 2) ** 0.5

    max_dist = 0
    idx = 0
    for i in range(1, len(ring) - 1):
        d = _perp_dist(ring[i], ring[0], ring[-1])
        if d > max_dist:
            max_dist = d
            idx = i

    if max_dist > epsilon:
        left = _simplify_ring(ring[:idx + 1], epsilon)
        right = _simplify_ring(ring[idx:], epsilon)
        return left[:-1] + right
    return [ring[0], ring[-1]]


def _simplify_geometry(geom: dict) -> dict:
    """Simplify polygon/multipolygon geometry for map display."""
    gtype = geom.get("type", "")
    if gtype == "Polygon":
        simplified = [_simplify_ring(ring, _SIMPLIFY_EPSILON) for ring in geom["coordinates"]]
        return {"type": "Polygon", "coordinates": simplified}
    elif gtype == "MultiPolygon":
        simplified = [
            [_simplify_ring(ring, _SIMPLIFY_EPSILON) for ring in poly]
            for poly in geom["coordinates"]
        ]
        return {"type": "MultiPolygon", "coordinates": simplified}
    return geom


def query_bbox(
    west: float, south: float, east: float, north: float,
    categories: list[str] | None = None,
) -> dict:
    """Filter in-memory cache by bbox overlap. Returns GeoJSON FeatureCollection."""
    if _feature_cache is None:
        return {"type": "FeatureCollection", "features": []}

    results = []
    for item in _feature_cache:
        bb = item["bbox"]  # (min_lat, max_lat, min_lon, max_lon)
        # Skip if no overlap
        if bb[1] < south or bb[0] > north or bb[3] < west or bb[2] > east:
            continue
        if categories and item["feature"]["properties"]["category"] not in categories:
            continue
        results.append(item["simplified"])

    return {"type": "FeatureCollection", "features": results}


def get_cache_status() -> dict:
    """Return cache statistics."""
    session = SessionLocal()
    try:
        metas = session.scalars(select(FaaAirspaceMeta)).all()
        sources = {}
        for m in metas:
            sources[m.source] = {
                "record_count": m.record_count,
                "last_edit_date": m.last_edit_date,
                "last_fetched_at": m.last_fetched_at.isoformat() if m.last_fetched_at else None,
                "last_checked_at": m.last_checked_at.isoformat() if m.last_checked_at else None,
            }
        return {
            "cache_loaded": _feature_cache is not None,
            "cache_size": len(_feature_cache) if _feature_cache else 0,
            "cache_loaded_at": datetime.fromtimestamp(_cache_loaded_at, tz=timezone.utc).isoformat() if _cache_loaded_at else None,
            "sources": sources,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# ArcGIS fetching
# ---------------------------------------------------------------------------

async def _fetch_arcgis_paginated(
    client: httpx.AsyncClient,
    base_url: str,
    where: str,
    out_fields: str,
) -> list[dict]:
    """Paginated GeoJSON fetch from an ArcGIS FeatureServer."""
    all_features: list[dict] = []
    offset = 0

    while True:
        params = {
            "where": where,
            "outFields": out_fields,
            "f": "geojson",
            "outSR": "4326",
            "resultRecordCount": str(PAGE_SIZE),
            "resultOffset": str(offset),
        }
        resp = await client.get(f"{base_url}/query", params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        features = data.get("features", [])
        all_features.extend(features)
        if len(features) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return all_features


async def _check_freshness(client: httpx.AsyncClient, source: str) -> tuple[bool, str | None]:
    """Check ArcGIS service metadata for lastEditDate.
    Returns (is_stale, new_edit_date_str)."""
    cfg = _SOURCES[source]
    checked_at = datetime.now(timezone.utc)
    try:
        resp = await client.get(f"{cfg['base']}?f=json", timeout=15)
        resp.raise_for_status()
        info = resp.json()
        edit_info = info.get("editingInfo", {})
        last_edit_ms = edit_info.get("lastEditDate")
        if last_edit_ms is None:
            # No edit info available, assume stale to be safe
            return True, None
        new_edit_date = str(last_edit_ms)
    except Exception:
        logger.warning("Could not check freshness for %s", source)
        return False, None

    session = SessionLocal()
    try:
        meta = session.scalars(
            select(FaaAirspaceMeta).where(FaaAirspaceMeta.source == source)
        ).first()
        if meta is None:
            session.add(FaaAirspaceMeta(
                source=source,
                last_edit_date=None,
                record_count=0,
                last_checked_at=checked_at,
            ))
            session.commit()
            return True, new_edit_date

        meta.last_checked_at = checked_at
        session.commit()
        if meta.last_edit_date != new_edit_date or meta.record_count == 0:
            return True, new_edit_date
        return False, new_edit_date
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Normalization (ported from frontend faaAirspace.ts)
# ---------------------------------------------------------------------------

def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _datetime_or_none(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        timestamp = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None

    raw = value.strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        return _datetime_or_none(float(raw))

    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _flatten_properties(value: object, *, prefix: str = "") -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    flattened: dict[str, object] = {}
    for key, child in value.items():
        key_str = str(key)
        flat_key = f"{prefix}.{key_str}" if prefix else key_str
        flattened[flat_key] = child
        if isinstance(child, dict):
            flattened.update(_flatten_properties(child, prefix=flat_key))
    return flattened


def _first_property(properties: dict, names: tuple[str, ...]):
    flat = _flatten_properties(properties)
    lowered = {key.lower().split(".")[-1]: value for key, value in flat.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _clean_match_value(value: object) -> str:
    text = str(value or "").upper()
    text = re.sub(r"\b(NATIONAL DEFENSE AIRSPACE|TEMPORARY FLIGHT RESTRICTION|TFR)\b", " ", text)
    return re.sub(r"[^A-Z0-9]+", "", text)


def _timing_from_notam_properties(properties: dict) -> dict[str, object] | None:
    notam_id = _first_property(
        properties,
        ("notam_id", "notamId", "notamID", "notamNumber", "notamKey", "NOTAM_KEY", "number", "id"),
    )
    effective_start = _datetime_or_none(_first_property(
        properties,
        (
            "effectiveStart",
            "effective_start",
            "effectiveStartDate",
            "startDate",
            "startTime",
            "validFrom",
            "beginDate",
            "begin",
            "start",
        ),
    ))
    effective_end = _datetime_or_none(_first_property(
        properties,
        (
            "effectiveEnd",
            "effective_end",
            "effectiveEndDate",
            "endDate",
            "endTime",
            "validTo",
            "expireDate",
            "expirationDate",
            "end",
        ),
    ))
    notice_time = _datetime_or_none(_first_property(
        properties,
        (
            "noticeTime",
            "notice_time",
            "issued",
            "issuedDate",
            "issueDate",
            "created",
            "LAST_MODIFICATION_DATETIME",
            "lastModificationDateTime",
        ),
    ))
    if not (notam_id or effective_start or effective_end or notice_time):
        return None
    return {
        "notam_id": str(notam_id) if notam_id else None,
        "effective_start": effective_start,
        "effective_end": effective_end,
        "notice_time": notice_time,
    }


def _notam_record_keys(properties: dict) -> set[str]:
    keys: set[str] = set()
    notam_id = _first_property(
        properties,
        ("notam_id", "notamId", "notamID", "notamNumber", "notamKey", "NOTAM_KEY", "number", "id"),
    )
    if notam_id:
        keys.add(f"id:{_clean_match_value(notam_id)}")

    title = _first_property(properties, ("title", "TITLE", "name", "NAME", "description"))
    if title:
        cleaned = _clean_match_value(title)
        if cleaned:
            keys.add(f"name:{cleaned}")

    city = _first_property(properties, ("city", "CITY", "location", "LOCATION"))
    state = _first_property(properties, ("state", "STATE"))
    if city:
        city_key = _clean_match_value(city)
        state_key = _clean_match_value(state) if state else ""
        if city_key:
            keys.add(f"loc:{city_key}:{state_key}")
    return keys


def _tfr_feature_keys(properties: dict) -> set[str]:
    keys: set[str] = set()
    for field in ("NOTAM_ID", "NOTAM_KEY", "notam_id", "notamId"):
        if properties.get(field):
            keys.add(f"id:{_clean_match_value(properties[field])}")

    name = properties.get("NAME") or properties.get("TITLE") or properties.get("name")
    if name:
        cleaned = _clean_match_value(name)
        if cleaned:
            keys.add(f"name:{cleaned}")

    city = properties.get("CITY") or properties.get("city")
    state = properties.get("STATE") or properties.get("state")
    if city:
        city_key = _clean_match_value(city)
        state_key = _clean_match_value(state) if state else ""
        if city_key:
            keys.add(f"loc:{city_key}:{state_key}")
    return keys


def _iter_notam_records(data: object) -> list[dict]:
    if isinstance(data, dict):
        if isinstance(data.get("features"), list):
            return [item for item in data["features"] if isinstance(item, dict)]
        for key in ("items", "notams", "results", "data"):
            child = data.get(key)
            if isinstance(child, list):
                return [item for item in child if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


async def _fetch_notam_timing_index(
    client: httpx.AsyncClient,
    credentials: FaaNotamsCredentials,
) -> dict[str, dict[str, object]]:
    if not credentials.enabled or not credentials.configured:
        return {}

    url = build_faa_notams_query_url(credentials.base_url)
    try:
        response = await client.get(
            url,
            params={"format": "geoJson"},
            headers=credentials.auth_headers(),
            timeout=30,
        )
        if response.status_code in {401, 403}:
            logger.warning("FAA NOTAMS API rejected credentials while enriching TFRs (%s)", response.status_code)
            return {}
        response.raise_for_status()
        data = response.json()
    except Exception:
        logger.warning("FAA NOTAMS API timing enrichment failed; keeping public TFR geometry only.", exc_info=True)
        return {}

    index: dict[str, dict[str, object]] = {}
    for record in _iter_notam_records(data):
        properties = record.get("properties") if isinstance(record.get("properties"), dict) else record
        timing = _timing_from_notam_properties(properties)
        if timing is None:
            continue
        for key in _notam_record_keys(properties):
            index.setdefault(key, timing)
    return index


async def _enrich_tfr_features_with_notam_timing(client: httpx.AsyncClient, features: list[dict]) -> list[dict]:
    session = SessionLocal()
    try:
        credentials = get_effective_faa_notams_credentials(session)
    finally:
        session.close()

    timing_index = await _fetch_notam_timing_index(client, credentials)
    if not timing_index:
        return features

    enriched: list[dict] = []
    for feature in features:
        properties = feature.get("properties", {})
        timing = None
        for key in _tfr_feature_keys(properties):
            timing = timing_index.get(key)
            if timing is not None:
                break
        if timing is None:
            enriched.append(feature)
            continue
        copied = dict(feature)
        copied["properties"] = {**properties, "_notam_timing": timing}
        enriched.append(copied)
    return enriched


def _normalize_class(f: dict) -> dict:
    p = f.get("properties", {})
    class_val = (p.get("CLASS") or "").upper()
    local_type = (p.get("LOCAL_TYPE") or "").upper()

    category = "E"
    if class_val == "B" or local_type == "CLASS_B":
        category = "B"
    elif class_val == "C" or local_type == "CLASS_C":
        category = "C"
    elif class_val == "D" or local_type == "CLASS_D":
        category = "D"
    elif class_val == "E" or local_type.startswith("CLASS_E"):
        category = "E"
    elif local_type == "MODE C" or (p.get("TYPE_CODE") or "").upper() == "MODE-C":
        category = "MODE-C"

    upper_val = p.get("UPPER_VAL")
    lower_val = p.get("LOWER_VAL")

    return {
        "type": "Feature",
        "geometry": f["geometry"],
        "properties": {
            "category": category,
            "name": p.get("NAME") or p.get("IDENT") or "Unknown",
            "ident": p.get("IDENT"),
            "upperVal": _float_or_none(upper_val),
            "upperUom": p.get("UPPER_UOM") or "FT",
            "lowerVal": _float_or_none(lower_val),
            "lowerUom": p.get("LOWER_UOM") or "FT",
            "upperDesc": p.get("UPPER_DESC") or "",
            "lowerDesc": p.get("LOWER_DESC") or "",
            "city": p.get("CITY"),
            "state": p.get("STATE"),
            "source": "class",
        },
    }


def _normalize_sua(f: dict) -> dict:
    p = f.get("properties", {})
    type_code = (p.get("TYPE_CODE") or "").upper()

    category = "R"
    if type_code == "P":
        category = "P"
    elif type_code == "R":
        category = "R"
    elif type_code == "W":
        category = "W"
    elif type_code == "A":
        category = "A"
    elif type_code in ("M", "MOA"):
        category = "MOA"

    upper_val = p.get("UPPER_VAL")
    lower_val = p.get("LOWER_VAL")

    return {
        "type": "Feature",
        "geometry": f["geometry"],
        "properties": {
            "category": category,
            "name": p.get("NAME") or "Unknown",
            "ident": None,
            "upperVal": _float_or_none(upper_val),
            "upperUom": p.get("UPPER_UOM") or "FT",
            "lowerVal": _float_or_none(lower_val),
            "lowerUom": p.get("LOWER_UOM") or "FT",
            "upperDesc": p.get("UPPER_DESC") or "",
            "lowerDesc": p.get("LOWER_DESC") or "",
            "city": p.get("CITY"),
            "state": p.get("STATE"),
            "source": "sua",
        },
    }


def _normalize_tfr(f: dict) -> dict:
    p = f.get("properties", {})
    timing = p.get("_notam_timing") if isinstance(p.get("_notam_timing"), dict) else {}
    notam_id = timing.get("notam_id") or _first_property(
        p,
        ("notam_id", "notamId", "notamID", "NOTAM_ID", "notamKey", "NOTAM_KEY", "number", "id"),
    )
    effective_start = _datetime_or_none(timing.get("effective_start")) or _datetime_or_none(_first_property(
        p,
        ("effectiveStart", "effective_start", "effectiveStartDate", "startDate", "startTime", "validFrom", "beginDate", "start"),
    ))
    effective_end = _datetime_or_none(timing.get("effective_end")) or _datetime_or_none(_first_property(
        p,
        ("effectiveEnd", "effective_end", "effectiveEndDate", "endDate", "endTime", "validTo", "expireDate", "expirationDate", "end"),
    ))
    notice_time = _datetime_or_none(timing.get("notice_time")) or _datetime_or_none(_first_property(
        p,
        ("noticeTime", "notice_time", "issued", "issuedDate", "issueDate", "created", "LAST_MODIFICATION_DATETIME"),
    ))
    return {
        "type": "Feature",
        "geometry": f["geometry"],
        "properties": {
            "category": "TFR",
            "name": p.get("NAME") or "TFR",
            "ident": None,
            "notamId": str(notam_id) if notam_id else None,
            "upperVal": None,
            "upperUom": "FT",
            "lowerVal": None,
            "lowerUom": "FT",
            "upperDesc": p.get("WKHR_RMK") or "",
            "lowerDesc": "",
            "city": p.get("CITY"),
            "state": p.get("STATE"),
            "effectiveStart": effective_start,
            "effectiveEnd": effective_end,
            "noticeTime": notice_time,
            "source": "tfr",
        },
    }


_NORMALIZERS = {
    "class": _normalize_class,
    "sua": _normalize_sua,
    "tfr": _normalize_tfr,
}


# ---------------------------------------------------------------------------
# Bbox computation
# ---------------------------------------------------------------------------

def _compute_bbox(geometry: dict) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lon, max_lon) from GeoJSON geometry."""
    gtype = geometry.get("type", "")
    coords = geometry.get("coordinates", [])

    if gtype == "Polygon":
        rings = coords
    elif gtype == "MultiPolygon":
        rings = [ring for poly in coords for ring in poly]
    else:
        return (0.0, 0.0, 0.0, 0.0)

    lats: list[float] = []
    lons: list[float] = []
    for ring in rings:
        for pt in ring:
            lons.append(pt[0])
            lats.append(pt[1])

    if not lats:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(lats), max(lats), min(lons), max(lons))


# ---------------------------------------------------------------------------
# DB import
# ---------------------------------------------------------------------------

def _import_to_db(source: str, features: list[dict], edit_date: str | None) -> int:
    """Delete old rows for this source, insert new normalized features, update meta."""
    if not features:
        logger.warning("FAA airspace: skipping %s import — 0 features returned (keeping existing data)", source)
        return 0

    normalizer = _NORMALIZERS[source]
    session = SessionLocal()
    try:
        session.execute(delete(FaaAirspaceFeature).where(FaaAirspaceFeature.source == source))

        count = 0
        for raw in features:
            norm = normalizer(raw)
            geom = norm["geometry"]
            if geom is None:
                continue
            props = norm["properties"]
            bbox = _compute_bbox(geom)

            session.add(FaaAirspaceFeature(
                source=props["source"],
                category=props["category"],
                name=props["name"],
                ident=props.get("ident"),
                upper_val=props["upperVal"],
                upper_uom=props["upperUom"],
                lower_val=props["lowerVal"],
                lower_uom=props["lowerUom"],
                upper_desc=props["upperDesc"],
                lower_desc=props["lowerDesc"],
                city=props.get("city"),
                state=props.get("state"),
                notam_id=props.get("notamId"),
                effective_start=props.get("effectiveStart"),
                effective_end=props.get("effectiveEnd"),
                notice_time=props.get("noticeTime"),
                min_lat=bbox[0],
                max_lat=bbox[1],
                min_lon=bbox[2],
                max_lon=bbox[3],
                geometry_json=geom,
            ))
            count += 1

        # Upsert meta
        meta = session.scalars(
            select(FaaAirspaceMeta).where(FaaAirspaceMeta.source == source)
        ).first()
        now = datetime.now(timezone.utc)
        if meta:
            meta.last_edit_date = edit_date
            meta.record_count = count
            meta.last_fetched_at = now
            meta.last_checked_at = now
        else:
            session.add(FaaAirspaceMeta(
                source=source,
                last_edit_date=edit_date,
                record_count=count,
                last_fetched_at=now,
                last_checked_at=now,
            ))

        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Load DB → memory cache
# ---------------------------------------------------------------------------

def _load_cache_from_db() -> int:
    """Load all FaaAirspaceFeature rows into the in-memory cache."""
    global _feature_cache, _cache_loaded_at

    session = SessionLocal()
    try:
        rows = session.scalars(select(FaaAirspaceFeature)).all()
        cache = []
        for r in rows:
            feature = {
                "type": "Feature",
                "geometry": r.geometry_json,
                "properties": {
                    "category": r.category,
                    "name": r.name,
                    "ident": r.ident,
                    "upperVal": r.upper_val,
                    "upperUom": r.upper_uom,
                    "lowerVal": r.lower_val,
                    "lowerUom": r.lower_uom,
                    "upperDesc": r.upper_desc,
                    "lowerDesc": r.lower_desc,
                    "city": r.city,
                    "state": r.state,
                    "notamId": r.notam_id,
                    "effectiveStart": _iso_or_none(r.effective_start),
                    "effectiveEnd": _iso_or_none(r.effective_end),
                    "noticeTime": _iso_or_none(r.notice_time),
                    "source": r.source,
                },
            }
            simplified = {
                "type": "Feature",
                "geometry": _simplify_geometry(r.geometry_json),
                "properties": feature["properties"],
            }
            cache.append({
                "feature": feature,
                "simplified": simplified,
                "bbox": (r.min_lat, r.max_lat, r.min_lon, r.max_lon),
            })
        # Atomic swap
        _feature_cache = cache
        _cache_loaded_at = time.time()
        return len(cache)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Background refresh tasks
# ---------------------------------------------------------------------------

async def _fetch_and_import(source: str) -> int:
    """Fetch from FAA ArcGIS and import into DB."""
    cfg = _SOURCES[source]
    async with httpx.AsyncClient() as client:
        logger.info("FAA airspace: fetching %s from ArcGIS...", source)

        where_clauses = cfg["where"]
        if isinstance(where_clauses, list):
            # Multiple queries (e.g. per-class) — fetch separately to avoid timeouts
            raw_features: list[dict] = []
            for wc in where_clauses:
                batch = await _fetch_arcgis_paginated(
                    client, cfg["base"], wc, cfg["fields"],
                )
                raw_features.extend(batch)
                logger.info("FAA airspace: %s query '%s' returned %d features", source, wc, len(batch))
        else:
            raw_features = await _fetch_arcgis_paginated(
                client, cfg["base"], where_clauses, cfg["fields"],
            )

        if source == "tfr":
            raw_features = await _enrich_tfr_features_with_notam_timing(client, raw_features)

        # Check edit date for meta
        is_stale, edit_date = await _check_freshness(client, source)

    count = _import_to_db(source, raw_features, edit_date)
    logger.info("FAA airspace: imported %d %s features", count, source)
    return count


async def _refresh_loop_main():
    """Background loop for class + SUA airspace (6-hour interval)."""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                for src in ("class", "sua"):
                    is_stale, edit_date = await _check_freshness(client, src)
                    if is_stale:
                        logger.info("FAA airspace: %s data is stale, re-importing...", src)
                        await _fetch_and_import(src)
                        _load_cache_from_db()
                    else:
                        logger.debug("FAA airspace: %s data is current", src)
        except Exception:
            logger.exception("FAA airspace refresh (class/sua) failed")

        await asyncio.sleep(6 * 3600)  # 6 hours


async def _refresh_loop_tfr():
    """Background loop for TFRs (30-minute interval)."""
    while True:
        try:
            async with httpx.AsyncClient() as client:
                is_stale, edit_date = await _check_freshness(client, "tfr")
                if is_stale:
                    logger.info("FAA airspace: TFR data is stale, re-importing...")
                    await _fetch_and_import("tfr")
                    _load_cache_from_db()
                else:
                    logger.debug("FAA airspace: TFR data is current")
        except Exception:
            logger.exception("FAA airspace refresh (tfr) failed")

        await asyncio.sleep(30 * 60)  # 30 minutes


async def start_faa_airspace_refresh() -> asyncio.Task:
    """Start background refresh tasks. Called from FastAPI lifespan."""

    # 1. Load existing data from DB into memory
    count = _load_cache_from_db()

    if count > 0:
        logger.info("FAA airspace: loaded %d features from DB", count)
    else:
        # DB is empty — do initial import
        logger.info("FAA airspace: DB empty, running initial import from FAA...")
        for src in ("class", "sua", "tfr"):
            try:
                await _fetch_and_import(src)
            except Exception:
                logger.exception("FAA airspace: initial import of %s failed", src)
        count = _load_cache_from_db()
        logger.info("FAA airspace: initial import complete — %d features", count)

    # 2. Launch background loops
    main_task = asyncio.create_task(_refresh_loop_main())
    tfr_task = asyncio.create_task(_refresh_loop_tfr())

    # Return a wrapper task that keeps both alive
    async def _keep_alive():
        await asyncio.gather(main_task, tfr_task)

    return asyncio.create_task(_keep_alive())
