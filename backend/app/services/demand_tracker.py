"""Demand tracker for raster pre-generation.

Records which (model, variable) combinations have been viewed by users so the
raster scheduler can warm the cache before users return.

Uses the same SQLite database as raster_cache.py (CACHE_ROOT/raster_cache.db)
but a separate table: demand_pairs.
"""
from __future__ import annotations

import logging
import sqlite3
import time

from app.services.raster_cache import CACHE_ROOT, DB_PATH

logger = logging.getLogger(__name__)

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """Return a module-level SQLite connection, creating the demand table if needed."""
    global _conn
    if _conn is not None:
        return _conn

    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.execute("""
        CREATE TABLE IF NOT EXISTS demand_pairs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            model           TEXT NOT NULL,
            variable        TEXT NOT NULL,
            last_viewed_at  REAL NOT NULL,
            view_count      INTEGER DEFAULT 1,
            UNIQUE(model, variable)
        )
    """)
    _conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_demand_pairs_last
        ON demand_pairs(last_viewed_at)
    """)
    _conn.commit()
    return _conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_view(model: str, variable: str) -> None:
    """Record or update a demand entry for the given model/variable pair.

    UPSERT: increments view_count and updates last_viewed_at on conflict.
    Safe to call synchronously from the request path (single SQLite write).
    """
    try:
        conn = _get_conn()
        now = time.time()
        conn.execute(
            """
            INSERT INTO demand_pairs (model, variable, last_viewed_at, view_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(model, variable) DO UPDATE SET
                last_viewed_at = excluded.last_viewed_at,
                view_count     = view_count + 1
            """,
            (model, variable, now),
        )
        conn.commit()
    except Exception:
        logger.warning(
            "demand_tracker: failed to record view for %s/%s", model, variable,
            exc_info=True,
        )


def get_active_demands(stale_days: int = 14) -> list[dict]:
    """Return all demand pairs viewed within the last *stale_days* days.

    Each entry is a dict with keys: model, variable, last_viewed_at, view_count.
    """
    try:
        conn = _get_conn()
        cutoff = time.time() - (stale_days * 86400)
        rows = conn.execute(
            """
            SELECT model, variable, last_viewed_at, view_count
            FROM demand_pairs
            WHERE last_viewed_at >= ?
            ORDER BY last_viewed_at DESC
            """,
            (cutoff,),
        ).fetchall()
        return [
            {
                "model": row[0],
                "variable": row[1],
                "last_viewed_at": row[2],
                "view_count": row[3],
            }
            for row in rows
        ]
    except Exception:
        logger.warning("demand_tracker: failed to get active demands", exc_info=True)
        return []


def prune_stale_demands(stale_days: int = 30) -> int:
    """Delete demand rows not viewed in *stale_days* days.

    Returns the number of rows deleted.
    """
    try:
        conn = _get_conn()
        cutoff = time.time() - (stale_days * 86400)
        cursor = conn.execute(
            "DELETE FROM demand_pairs WHERE last_viewed_at < ?",
            (cutoff,),
        )
        conn.commit()
        deleted = cursor.rowcount
        if deleted:
            logger.info(
                "demand_tracker: pruned %d stale demand entries (>%d days old)",
                deleted,
                stale_days,
            )
        return deleted
    except Exception:
        logger.warning("demand_tracker: failed to prune stale demands", exc_info=True)
        return 0
