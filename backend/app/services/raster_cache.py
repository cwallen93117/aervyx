"""Persistent raster cache — filesystem PNGs + SQLite metadata.

Stores generated weather overlay PNGs on disk so they survive restarts.
Metadata (coordinates, tiers, debug labels, etc.) lives in SQLite for
fast lookups. Auto-prunes data older than *keep_days*.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
CACHE_ROOT = Path(os.environ.get("RASTER_CACHE_DIR", "/app/storage/raster_cache"))
DB_PATH = CACHE_ROOT / "raster_cache.db"

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """Return a module-level SQLite connection, creating schema if needed."""
    global _conn
    if _conn is not None:
        return _conn

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS raster_cache (
            cache_key       TEXT PRIMARY KEY,
            model           TEXT NOT NULL,
            run_date        TEXT NOT NULL,
            run_hour        INTEGER NOT NULL,
            fxx             INTEGER NOT NULL,
            variable        TEXT NOT NULL,
            file_path       TEXT NOT NULL,
            coordinates_json TEXT NOT NULL,
            data_range_json  TEXT,
            tiers_json       TEXT,
            debug_labels_json TEXT,
            meta_json        TEXT,
            file_size_bytes  INTEGER DEFAULT 0,
            created_at       REAL NOT NULL
        )
    """)
    _conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_raster_cache_date
        ON raster_cache(run_date)
    """)
    _conn.commit()
    return _conn


def _rel_path(model: str, run_date: str, run_hour: int, variable: str, fxx: int) -> str:
    """Build the relative file path under CACHE_ROOT."""
    return f"{model}/{run_date}/{run_hour:02d}/{variable}_f{fxx:03d}.png"


def _grid_path(png_rel: str) -> str:
    """Grid data file path — sits next to the PNG."""
    return png_rel.rsplit(".", 1)[0] + ".grid"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_cached_raster(cache_key: str) -> dict[str, Any] | None:
    """Look up a cached raster by key.

    Returns the full response dict (with base64 PNG) if found, else None.
    """
    conn = _get_conn()
    row = conn.execute(
        "SELECT file_path, coordinates_json, data_range_json, tiers_json, "
        "debug_labels_json, meta_json FROM raster_cache WHERE cache_key = ?",
        (cache_key,),
    ).fetchone()

    if row is None:
        return None

    file_path, coords_json, range_json, tiers_json, debug_json, meta_json = row
    abs_path = CACHE_ROOT / file_path

    if not abs_path.exists():
        # Orphaned row — clean it up
        conn.execute("DELETE FROM raster_cache WHERE cache_key = ?", (cache_key,))
        conn.commit()
        return None

    try:
        png_bytes = abs_path.read_bytes()
    except OSError:
        logger.warning("Failed to read cached PNG %s", abs_path, exc_info=True)
        return None

    png_b64 = base64.b64encode(png_bytes).decode("ascii")

    result: dict[str, Any] = {
        "image": f"data:image/png;base64,{png_b64}",
        "coordinates": json.loads(coords_json),
    }
    if range_json:
        result["data_range"] = json.loads(range_json)
    if tiers_json:
        result["tiers"] = json.loads(tiers_json)
    # Legacy: skip debug_labels_json, dots are now generated on-the-fly
    if meta_json:
        result["meta"] = json.loads(meta_json)

    # Load compressed grid data if available (for on-the-fly dot generation)
    grid_file = CACHE_ROOT / _grid_path(file_path)
    if grid_file.exists():
        try:
            result["_grid_bytes"] = grid_file.read_bytes()
            # Parse shape + display_round from meta
            meta = result.get("meta", {})
            w = meta.get("width", 0)
            h = meta.get("height", 0)
            result["_grid_shape"] = (h, w)
            result["_display_round"] = meta.get("display_round", 1)
        except OSError:
            pass  # dots just won't show on this cache hit

    return result


def store_raster(
    cache_key: str,
    model: str,
    run_date: str,
    run_hour: int,
    fxx: int,
    variable: str,
    result: dict[str, Any],
) -> None:
    """Persist a raster result (base64 PNG + metadata) to disk + SQLite."""
    conn = _get_conn()

    # Decode the base64 PNG from the result dict
    image_data: str = result.get("image", "")
    if image_data.startswith("data:image/png;base64,"):
        image_data = image_data[len("data:image/png;base64,"):]
    png_bytes = base64.b64decode(image_data)

    rel = _rel_path(model, run_date, run_hour, variable, fxx)
    abs_path = CACHE_ROOT / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(png_bytes)

    # Save compressed grid data alongside the PNG for on-the-fly dot generation
    grid_data: bytes | None = result.get("_grid_bytes")
    if grid_data:
        grid_abs = CACHE_ROOT / _grid_path(rel)
        try:
            grid_abs.write_bytes(grid_data)
        except OSError:
            logger.warning("Failed to write grid data %s", grid_abs, exc_info=True)

    # Embed display_round in meta for cache retrieval
    meta = dict(result.get("meta") or {})
    if "_display_round" in result:
        meta["display_round"] = result["_display_round"]

    conn.execute(
        """
        INSERT INTO raster_cache
            (cache_key, model, run_date, run_hour, fxx, variable, file_path,
             coordinates_json, data_range_json, tiers_json, debug_labels_json,
             meta_json, file_size_bytes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            file_path       = excluded.file_path,
            coordinates_json = excluded.coordinates_json,
            data_range_json  = excluded.data_range_json,
            tiers_json       = excluded.tiers_json,
            debug_labels_json = excluded.debug_labels_json,
            meta_json        = excluded.meta_json,
            file_size_bytes  = excluded.file_size_bytes,
            created_at       = excluded.created_at
        """,
        (
            cache_key,
            model,
            run_date,
            int(run_hour),
            int(fxx),
            variable,
            rel,
            json.dumps(result.get("coordinates")),
            json.dumps(result.get("data_range")) if result.get("data_range") else None,
            json.dumps(result.get("tiers")) if result.get("tiers") else None,
            None,  # debug_labels no longer stored in DB — generated on-the-fly
            json.dumps(meta),
            len(png_bytes),
            time.time(),
        ),
    )
    conn.commit()
    logger.debug("Cached raster %s (%d bytes PNG, %d bytes grid)",
                 cache_key, len(png_bytes), len(grid_data) if grid_data else 0)


def prune_old_rasters(keep_days: int = 2) -> int:
    """Delete cached rasters older than *keep_days*. Returns count deleted."""
    conn = _get_conn()
    cutoff = time.time() - (keep_days * 86400)

    # Find distinct date directories to remove
    rows = conn.execute(
        "SELECT DISTINCT model, run_date FROM raster_cache WHERE created_at < ?",
        (cutoff,),
    ).fetchall()

    deleted = 0
    for model, run_date in rows:
        dir_path = CACHE_ROOT / model / run_date
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                logger.info("Pruned raster dir %s", dir_path)
            except OSError:
                logger.warning("Failed to prune dir %s", dir_path, exc_info=True)

    # Delete all old rows
    cursor = conn.execute(
        "DELETE FROM raster_cache WHERE created_at < ?", (cutoff,)
    )
    deleted = cursor.rowcount
    conn.commit()

    if deleted:
        logger.info("Pruned %d raster cache entries older than %d days", deleted, keep_days)
    return deleted


def cache_stats() -> dict[str, Any]:
    """Return summary statistics about the cache."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(file_size_bytes), 0) FROM raster_cache"
    ).fetchone()
    entry_count = row[0]
    total_bytes = row[1]
    return {
        "entry_count": entry_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 1),
    }
