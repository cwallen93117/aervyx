from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LivePosition, TrackingSession


# ---------------------------------------------------------------------------
# Internal asyncio pub/sub for SSE fan-out
# ---------------------------------------------------------------------------

_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}
logger = logging.getLogger("aervyx.tracking")


def subscribe(task_id: int) -> asyncio.Queue[dict[str, Any]]:
    """Register a new SSE subscriber for a given task. Returns a queue."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
    _subscribers.setdefault(task_id, set()).add(queue)
    return queue


def unsubscribe(task_id: int, queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a subscriber queue for a given task."""
    task_subs = _subscribers.get(task_id)
    if task_subs:
        task_subs.discard(queue)
        if not task_subs:
            del _subscribers[task_id]


def _publish(task_id: int, message: dict[str, Any]) -> None:
    """Fan out a message to all SSE subscribers for a task (non-blocking)."""
    task_subs = _subscribers.get(task_id)
    if not task_subs:
        return
    dead: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in task_subs:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(queue)
        except Exception:
            logger.warning("Dropping failed live-tracking subscriber for task %s", task_id, exc_info=True)
            dead.append(queue)
    for queue in dead:
        task_subs.discard(queue)
    if not task_subs:
        del _subscribers[task_id]


# ---------------------------------------------------------------------------
# Core tracking functions
# ---------------------------------------------------------------------------

def store_position(
    session: Session,
    *,
    task_id: int,
    lat: float,
    lon: float,
    alt: float | None = None,
    speed: float | None = None,
    heading: float | None = None,
    accuracy: float | None = None,
    timestamp: datetime | None = None,
    source: str | None = None,
    device_id: str | None = None,
    battery_level: int | None = None,
    pilot_id: int | None = None,
) -> LivePosition:
    """Persist a position fix and fan it out to SSE subscribers."""
    ts = timestamp or datetime.now(UTC)
    pos = LivePosition(
        id=uuid.uuid4(),
        pilot_id=pilot_id,
        task_id=task_id,
        lat=lat,
        lon=lon,
        alt=alt,
        speed=speed,
        heading=heading,
        accuracy=accuracy,
        timestamp=ts,
        source=source,
        device_id=device_id,
        battery_level=battery_level,
    )
    session.add(pos)

    # Upsert tracking session --------------------------------------------------
    tracking = session.scalar(
        select(TrackingSession).where(
            TrackingSession.task_id == task_id,
            TrackingSession.pilot_id == pilot_id,
            TrackingSession.is_active.is_(True),
        )
    ) if pilot_id is not None else None

    if tracking is not None:
        tracking.last_seen_at = ts
        tracking.position_count = (tracking.position_count or 0) + 1
    elif pilot_id is not None:
        tracking = TrackingSession(
            id=uuid.uuid4(),
            pilot_id=pilot_id,
            task_id=task_id,
            started_at=ts,
            last_seen_at=ts,
            is_active=True,
            position_count=1,
        )
        session.add(tracking)

    session.flush()

    # Fan out to SSE subscribers ------------------------------------------------
    message = {
        "id": str(pos.id),
        "pilot_id": pos.pilot_id,
        "task_id": pos.task_id,
        "lat": pos.lat,
        "lon": pos.lon,
        "alt": pos.alt,
        "speed": pos.speed,
        "heading": pos.heading,
        "accuracy": pos.accuracy,
        "timestamp": ts.isoformat(),
        "source": pos.source,
        "device_id": pos.device_id,
        "battery_level": pos.battery_level,
    }
    _publish(task_id, message)

    return pos


def get_live_positions(session: Session, task_id: int) -> list[dict[str, Any]]:
    """Return the latest position per pilot for a task (active sessions only).

    Uses a window function to get the latest position per active pilot in one query.
    """
    from sqlalchemy import func as sa_func

    active_pilots = session.scalars(
        select(TrackingSession.pilot_id).where(
            TrackingSession.task_id == task_id,
            TrackingSession.is_active.is_(True),
        )
    ).all()

    if not active_pilots:
        return []

    # Use a subquery with ROW_NUMBER() to get latest position per pilot
    row_num = sa_func.row_number().over(
        partition_by=LivePosition.pilot_id,
        order_by=LivePosition.timestamp.desc(),
    ).label("rn")

    subq = (
        select(LivePosition, row_num)
        .where(
            LivePosition.task_id == task_id,
            LivePosition.pilot_id.in_(active_pilots),
        )
        .subquery()
    )

    rows = session.execute(
        select(subq).where(subq.c.rn == 1)
    ).all()

    return [
        {
            "id": str(row.id),
            "pilot_id": row.pilot_id,
            "task_id": row.task_id,
            "lat": row.lat,
            "lon": row.lon,
            "alt": row.alt,
            "speed": row.speed,
            "heading": row.heading,
            "accuracy": row.accuracy,
            "timestamp": row.timestamp.isoformat(),
            "source": row.source,
            "device_id": row.device_id,
            "battery_level": row.battery_level,
        }
        for row in rows
    ]


def get_position_history(
    session: Session,
    task_id: int,
    *,
    pilot_id: int | None = None,
    since: datetime | None = None,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    """Return historical positions for a task, optionally filtered by pilot and time."""
    query = select(LivePosition).where(LivePosition.task_id == task_id)
    if pilot_id is not None:
        query = query.where(LivePosition.pilot_id == pilot_id)
    if since is not None:
        query = query.where(LivePosition.timestamp >= since)
    query = query.order_by(LivePosition.timestamp.asc()).limit(limit)

    rows = session.scalars(query).all()
    return [
        {
            "id": str(pos.id),
            "pilot_id": pos.pilot_id,
            "task_id": pos.task_id,
            "lat": pos.lat,
            "lon": pos.lon,
            "alt": pos.alt,
            "speed": pos.speed,
            "heading": pos.heading,
            "accuracy": pos.accuracy,
            "timestamp": pos.timestamp.isoformat(),
            "source": pos.source,
            "device_id": pos.device_id,
            "battery_level": pos.battery_level,
        }
        for pos in rows
    ]
