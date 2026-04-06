"""FAA Airspace API — serves cached airspace data from memory."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services.faa_airspace import get_cache_status, query_bbox

router = APIRouter(prefix="/api/faa-airspace", tags=["faa-airspace"])


@router.get("/features")
async def get_features(
    west: float = Query(..., ge=-180, le=180),
    south: float = Query(..., ge=-90, le=90),
    east: float = Query(..., ge=-180, le=180),
    north: float = Query(..., ge=-90, le=90),
    categories: str = Query("", description="Comma-separated category list (e.g. B,C,D,P,R,TFR)"),
) -> JSONResponse:
    """Return GeoJSON FeatureCollection filtered by bounding box and optional categories."""
    cat_list = [c.strip() for c in categories.split(",") if c.strip()] or None
    fc = query_bbox(west, south, east, north, cat_list)
    return JSONResponse(content=fc)


@router.get("/status")
async def get_status() -> dict:
    """Return cache status: per-source counts, timestamps, edit dates."""
    return get_cache_status()
