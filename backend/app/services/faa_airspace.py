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
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.models import FaaAirspaceFeature, FaaAirspaceMeta

logger = logging.getLogger("faa_airspace")

# ---------------------------------------------------------------------------
# ArcGIS endpoint configuration
# ---------------------------------------------------------------------------

_SOURCES = {
    "class": {
        "base": "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/arcgis/rest/services/Class_Airspace/FeatureServer/0",
        "fields": "IDENT,NAME,CLASS,LOCAL_TYPE,TYPE_CODE,UPPER_DESC,LOWER_DESC,UPPER_VAL,UPPER_UOM,LOWER_VAL,LOWER_UOM,CITY,STATE",
        "where": "CLASS IN ('B','C','D') OR LOCAL_TYPE IN ('CLASS_B','CLASS_C','CLASS_D')",
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

PAGE_SIZE = 2000

# ---------------------------------------------------------------------------
# In-memory cache
# ---------------------------------------------------------------------------

# List of dicts: {"feature": <GeoJSON Feature dict>, "bbox": (min_lat, max_lat, min_lon, max_lon)}
_feature_cache: list[dict] | None = None
_cache_loaded_at: float = 0.0


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
        results.append(item["feature"])

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
        if meta is None or meta.last_edit_date != new_edit_date or meta.record_count == 0:
            return True, new_edit_date
        return False, new_edit_date
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Normalization (ported from frontend faaAirspace.ts)
# ---------------------------------------------------------------------------

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
            "upperVal": float(upper_val) if upper_val is not None else None,
            "upperUom": p.get("UPPER_UOM") or "FT",
            "lowerVal": float(lower_val) if lower_val is not None else None,
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
            "upperVal": float(upper_val) if upper_val is not None else None,
            "upperUom": p.get("UPPER_UOM") or "FT",
            "lowerVal": float(lower_val) if lower_val is not None else None,
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
    return {
        "type": "Feature",
        "geometry": f["geometry"],
        "properties": {
            "category": "TFR",
            "name": p.get("NAME") or "TFR",
            "ident": None,
            "upperVal": None,
            "upperUom": "FT",
            "lowerVal": None,
            "lowerUom": "FT",
            "upperDesc": p.get("WKHR_RMK") or "",
            "lowerDesc": "",
            "city": p.get("CITY"),
            "state": p.get("STATE"),
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
        else:
            session.add(FaaAirspaceMeta(
                source=source,
                last_edit_date=edit_date,
                record_count=count,
                last_fetched_at=now,
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
                    "source": r.source,
                },
            }
            cache.append({
                "feature": feature,
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
        raw_features = await _fetch_arcgis_paginated(
            client, cfg["base"], cfg["where"], cfg["fields"],
        )

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
