"""FAA Airspace API — serves cached airspace data from memory."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.services.faa_airspace import get_cache_status, query_bbox

router = APIRouter(prefix="/api/faa-airspace", tags=["faa-airspace"])
logger = logging.getLogger("faa_airspace")

_manual_refresh_task: asyncio.Task | None = None
_manual_refresh_results: dict[str, dict[str, object]] = {}
_manual_refresh_started_at: str | None = None
_manual_refresh_completed_at: str | None = None


def _manual_refresh_state() -> dict[str, object]:
    in_progress = _manual_refresh_task is not None and not _manual_refresh_task.done()
    return {
        "in_progress": in_progress,
        "started_at": _manual_refresh_started_at,
        "completed_at": _manual_refresh_completed_at,
        "results": _manual_refresh_results,
    }


def _status_payload() -> dict:
    return {
        **get_cache_status(),
        "manual_refresh": _manual_refresh_state(),
        "refreshed": _manual_refresh_results,
    }


async def _run_manual_refresh() -> None:
    """Refresh FAA cache outside the request lifecycle so staging proxies do not time out."""
    global _manual_refresh_results, _manual_refresh_completed_at

    from app.services.faa_airspace import _fetch_and_import, _load_cache_from_db

    results: dict[str, dict[str, object]] = {}
    for src in ("class", "sua", "tfr"):
        try:
            count = await _fetch_and_import(src)
            results[src] = {"status": "ok", "count": count}
        except Exception as exc:
            logger.exception("FAA airspace manual refresh failed for %s", src)
            results[src] = {"status": "error", "error": str(exc)}

    try:
        loaded_count = _load_cache_from_db()
        results["cache"] = {"status": "ok", "count": loaded_count}
    except Exception as exc:
        logger.exception("FAA airspace manual cache reload failed")
        results["cache"] = {"status": "error", "error": str(exc)}

    _manual_refresh_results = results
    _manual_refresh_completed_at = datetime.now(timezone.utc).isoformat()


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
    return _status_payload()


@router.post("/refresh")
async def refresh_cache() -> JSONResponse:
    """Force re-import all sources from FAA ArcGIS without holding the HTTP request open."""
    global _manual_refresh_task, _manual_refresh_results, _manual_refresh_started_at, _manual_refresh_completed_at

    started = False
    if _manual_refresh_task is None or _manual_refresh_task.done():
        _manual_refresh_results = {}
        _manual_refresh_started_at = datetime.now(timezone.utc).isoformat()
        _manual_refresh_completed_at = None
        _manual_refresh_task = asyncio.create_task(_run_manual_refresh())
        started = True

    return JSONResponse(
        status_code=202 if started else 200,
        content={"refresh_started": started, **_status_payload()},
    )
