from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LivePosition, TrackingSession, User


# ---------------------------------------------------------------------------
# Internal asyncio pub/sub for SSE fan-out
# ---------------------------------------------------------------------------

_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}
_pilot_subscribers: dict[int, set[asyncio.Queue[dict[str, Any]]]] = {}
_global_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
logger = logging.getLogger("aervyx.tracking")
VALID_AIRCRAFT_ICONS = {"hang_glider", "paraglider", "sailplane"}
VALID_PROFILE_TYPES_ALL = {"pilot", "driver", "stationary_node"}


def _normalize_aircraft_icon(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    return candidate if candidate in VALID_AIRCRAFT_ICONS else "hang_glider"


def _normalize_profile_type(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    return candidate if candidate in VALID_PROFILE_TYPES_ALL else "pilot"


def normalize_position_source(raw: str | None) -> str:
    """Map raw LivePosition.source values to a public-facing ``cellular`` / ``mesh`` / ``other`` bucket.

    - ``app`` (mobile tracking app)        → ``cellular``
    - ``mqtt_gateway`` (Meshtastic bridge) → ``mesh``
    - anything else / unknown / ``None``   → ``other``
    """
    if raw is None:
        return "other"
    candidate = raw.strip().lower()
    if candidate == "app":
        return "cellular"
    if candidate == "mqtt_gateway":
        return "mesh"
    return "other"


def _aircraft_icons_by_pilot(session: Session, pilot_ids: list[int]) -> dict[int, str]:
    if not pilot_ids:
        return {}
    users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids)).order_by(User.id.asc())).all()
    aircraft_icons: dict[int, str] = {}
    for user in users:
        if user.pilot_id is not None and user.pilot_id not in aircraft_icons:
            aircraft_icons[user.pilot_id] = _normalize_aircraft_icon(user.aircraft_icon)
    return aircraft_icons


def _profile_types_by_pilot(session: Session, pilot_ids: list[int]) -> dict[int, str]:
    """Return a map of ``pilot_id → profile_type`` (``pilot`` / ``driver``) using the User table.

    Pilots without a linked User row fall through to the ``pilot`` default at call sites.
    """
    if not pilot_ids:
        return {}
    users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids)).order_by(User.id.asc())).all()
    profile_types: dict[int, str] = {}
    for user in users:
        if user.pilot_id is not None and user.pilot_id not in profile_types:
            profile_types[user.pilot_id] = _normalize_profile_type(user.profile_type)
    return profile_types


def _stationary_node_by_device(session: Session, device_ids: list[str]) -> dict[str, User]:
    """Return a map of ``device_id → User`` for any stationary-node users matching the given device IDs."""
    if not device_ids:
        return {}
    users = session.scalars(
        select(User).where(
            User.mesh_device_id.in_(device_ids),
            User.profile_type == "stationary_node",
        )
    ).all()
    return {user.mesh_device_id: user for user in users if user.mesh_device_id}


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
# Pilot-scoped pub/sub (for buddy group tracking)
# ---------------------------------------------------------------------------

def subscribe_pilots(pilot_ids: list[int]) -> asyncio.Queue[dict[str, Any]]:
    """Register a single queue that receives positions for any of the given pilot IDs."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
    for pid in pilot_ids:
        _pilot_subscribers.setdefault(pid, set()).add(queue)
    return queue


def unsubscribe_pilots(pilot_ids: list[int], queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a subscriber queue from all specified pilot channels."""
    for pid in pilot_ids:
        subs = _pilot_subscribers.get(pid)
        if subs:
            subs.discard(queue)
            if not subs:
                del _pilot_subscribers[pid]


def _publish_to_pilot_subscribers(pilot_id: int, message: dict[str, Any]) -> None:
    """Fan out a message to all SSE subscribers watching a specific pilot."""
    subs = _pilot_subscribers.get(pilot_id)
    if not subs:
        return
    dead: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in subs:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(queue)
        except Exception:
            logger.warning("Dropping failed pilot subscriber for pilot %s", pilot_id, exc_info=True)
            dead.append(queue)
    for queue in dead:
        subs.discard(queue)
    if not subs:
        del _pilot_subscribers[pilot_id]


# ---------------------------------------------------------------------------
# Global pub/sub (debug mode — broadcasts every position to every subscriber)
# ---------------------------------------------------------------------------

def subscribe_global() -> asyncio.Queue[dict[str, Any]]:
    """Register a new SSE subscriber that receives EVERY incoming position."""
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=512)
    _global_subscribers.add(queue)
    return queue


def unsubscribe_global(queue: asyncio.Queue[dict[str, Any]]) -> None:
    """Remove a global SSE subscriber queue."""
    _global_subscribers.discard(queue)


def _publish_global(message: dict[str, Any]) -> None:
    """Fan out a message to all global SSE subscribers."""
    if not _global_subscribers:
        return
    dead: list[asyncio.Queue[dict[str, Any]]] = []
    for queue in _global_subscribers:
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            dead.append(queue)
        except Exception:
            logger.warning("Dropping failed global subscriber", exc_info=True)
            dead.append(queue)
    for queue in dead:
        _global_subscribers.discard(queue)


# ---------------------------------------------------------------------------
# Core tracking functions
# ---------------------------------------------------------------------------

def store_position(
    session: Session,
    *,
    task_id: int | None,
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

    # Upsert tracking session (for all positions, including free-flight) --------
    if pilot_id is not None:
        if task_id is not None:
            tracking = session.scalar(
                select(TrackingSession).where(
                    TrackingSession.task_id == task_id,
                    TrackingSession.pilot_id == pilot_id,
                    TrackingSession.is_active.is_(True),
                )
            )
        else:
            tracking = session.scalar(
                select(TrackingSession).where(
                    TrackingSession.task_id.is_(None),
                    TrackingSession.pilot_id == pilot_id,
                    TrackingSession.is_active.is_(True),
                )
            )

        if tracking is not None:
            tracking.last_seen_at = ts
            tracking.position_count = (tracking.position_count or 0) + 1
        else:
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

    # Build SSE message once for all fan-out paths -----------------------------
    has_any_subscribers = (
        (task_id is not None and task_id in _subscribers)
        or (pilot_id is not None and pilot_id in _pilot_subscribers)
        or bool(_global_subscribers)
    )
    if has_any_subscribers:
        # Resolve pilot name for display in "show all" debug view
        pilot_name: str | None = None
        aircraft_icon = "hang_glider"
        profile_type = "pilot"
        if pilot_id is not None:
            user = session.scalar(select(User).where(User.pilot_id == pilot_id))
            if user is not None:
                pilot_name = user.full_name
                aircraft_icon = _normalize_aircraft_icon(user.aircraft_icon)
                profile_type = _normalize_profile_type(user.profile_type)
        elif device_id:
            # No pilot attached — see if this is a registered stationary mesh node.
            stationary = session.scalar(
                select(User).where(
                    User.mesh_device_id == device_id,
                    User.profile_type == "stationary_node",
                )
            )
            if stationary is not None:
                pilot_name = stationary.full_name
                profile_type = "stationary_node"
        message = {
            "id": str(pos.id),
            "pilot_id": pos.pilot_id,
            "pilot_name": pilot_name,
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
            "aircraft_icon": aircraft_icon,
            "profile_type": profile_type,
            "position_source": normalize_position_source(pos.source),
        }
        if task_id is not None:
            _publish(task_id, message)
        if pilot_id is not None:
            _publish_to_pilot_subscribers(pilot_id, message)
        _publish_global(message)

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
    pilot_id_list = [pilot_id for pilot_id in active_pilots if pilot_id is not None]
    aircraft_icons_by_pilot = _aircraft_icons_by_pilot(session, pilot_id_list)
    profile_types_by_pilot = _profile_types_by_pilot(session, pilot_id_list)

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
            "aircraft_icon": aircraft_icons_by_pilot.get(row.pilot_id, "hang_glider"),
            "profile_type": profile_types_by_pilot.get(row.pilot_id, "pilot"),
            "position_source": normalize_position_source(row.source),
        }
        for row in rows
    ]


def get_all_active_positions(session: Session, minutes: int = 5) -> list[dict[str, Any]]:
    """Return latest position for every pilot with recent activity (any task or free-flight)."""
    from datetime import timedelta
    from sqlalchemy import func as sa_func

    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    active_sessions = session.scalars(
        select(TrackingSession).where(
            TrackingSession.is_active.is_(True),
            TrackingSession.last_seen_at >= cutoff,
        )
    ).all()

    if not active_sessions:
        return []

    pilot_ids = [s.pilot_id for s in active_sessions if s.pilot_id is not None]
    if not pilot_ids:
        return []

    aircraft_icons = _aircraft_icons_by_pilot(session, pilot_ids)
    profile_types = _profile_types_by_pilot(session, pilot_ids)

    # Pilot names via User table
    users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids))).all()
    pilot_names: dict[int, str] = {}
    for u in users:
        if u.pilot_id is not None and u.pilot_id not in pilot_names:
            pilot_names[u.pilot_id] = u.full_name

    # Latest position per pilot
    row_num = sa_func.row_number().over(
        partition_by=LivePosition.pilot_id,
        order_by=LivePosition.timestamp.desc(),
    ).label("rn")

    subq = (
        select(LivePosition, row_num)
        .where(
            LivePosition.pilot_id.in_(pilot_ids),
            LivePosition.timestamp >= cutoff,
        )
        .subquery()
    )

    rows = session.execute(select(subq).where(subq.c.rn == 1)).all()

    return [
        {
            "pilot_id": row.pilot_id,
            "pilot_name": pilot_names.get(row.pilot_id, f"Pilot {row.pilot_id}"),
            "lat": row.lat,
            "lon": row.lon,
            "alt": row.alt,
            "speed": row.speed,
            "heading": row.heading,
            "accuracy": row.accuracy,
            "timestamp": row.timestamp.isoformat(),
            "source": row.source,
            "battery_level": row.battery_level,
            "aircraft_icon": aircraft_icons.get(row.pilot_id, "hang_glider"),
            "profile_type": profile_types.get(row.pilot_id, "pilot"),
            "position_source": normalize_position_source(row.source),
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
    pilot_id_list = [pos.pilot_id for pos in rows if pos.pilot_id is not None]
    aircraft_icons_by_pilot = _aircraft_icons_by_pilot(session, pilot_id_list)
    profile_types_by_pilot = _profile_types_by_pilot(session, pilot_id_list)
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
            "aircraft_icon": aircraft_icons_by_pilot.get(pos.pilot_id, "hang_glider"),
            "profile_type": profile_types_by_pilot.get(pos.pilot_id, "pilot"),
            "position_source": normalize_position_source(pos.source),
        }
        for pos in rows
    ]


# ---------------------------------------------------------------------------
# Pilot-set queries (for buddy group tracking)
# ---------------------------------------------------------------------------

def get_live_positions_for_pilots(session: Session, pilot_ids: list[int]) -> list[dict[str, Any]]:
    """Return the latest position per pilot for a set of pilot IDs."""
    from sqlalchemy import func as sa_func

    if not pilot_ids:
        return []

    aircraft_icons = _aircraft_icons_by_pilot(session, pilot_ids)
    profile_types = _profile_types_by_pilot(session, pilot_ids)

    row_num = sa_func.row_number().over(
        partition_by=LivePosition.pilot_id,
        order_by=LivePosition.timestamp.desc(),
    ).label("rn")

    subq = (
        select(LivePosition, row_num)
        .where(LivePosition.pilot_id.in_(pilot_ids))
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
            "aircraft_icon": aircraft_icons.get(row.pilot_id, "hang_glider"),
            "profile_type": profile_types.get(row.pilot_id, "pilot"),
            "position_source": normalize_position_source(row.source),
        }
        for row in rows
    ]


def get_all_recent_positions(
    session: Session,
    *,
    minutes: int = 60,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    """Return every position record from the last `minutes` minutes (all pilots, all tasks).

    Used by the debug "show all" live tracking view. Intended to include free-flight
    positions as well (task_id IS NULL). Returned newest-first, limited to `limit` rows.
    """
    from datetime import timedelta

    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)

    rows = session.scalars(
        select(LivePosition)
        .where(LivePosition.timestamp >= cutoff)
        .order_by(LivePosition.timestamp.desc())
        .limit(limit)
    ).all()

    pilot_ids = [pos.pilot_id for pos in rows if pos.pilot_id is not None]
    aircraft_icons = _aircraft_icons_by_pilot(session, pilot_ids)
    profile_types = _profile_types_by_pilot(session, pilot_ids)

    pilot_names: dict[int, str] = {}
    if pilot_ids:
        users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids))).all()
        for u in users:
            if u.pilot_id is not None and u.pilot_id not in pilot_names:
                pilot_names[u.pilot_id] = u.full_name

    # Resolve stationary-node rows by device_id for unassigned positions.
    orphan_device_ids = {pos.device_id for pos in rows if pos.pilot_id is None and pos.device_id}
    stationary_by_device = _stationary_node_by_device(session, list(orphan_device_ids))

    def _profile_for(pos: LivePosition) -> str:
        if pos.pilot_id is not None:
            return profile_types.get(pos.pilot_id, "pilot")
        if pos.device_id and pos.device_id in stationary_by_device:
            return "stationary_node"
        return "pilot"

    def _name_for(pos: LivePosition) -> str | None:
        if pos.pilot_id is not None:
            return pilot_names.get(pos.pilot_id)
        if pos.device_id and pos.device_id in stationary_by_device:
            return stationary_by_device[pos.device_id].full_name
        return None

    return [
        {
            "id": str(pos.id),
            "pilot_id": pos.pilot_id,
            "pilot_name": _name_for(pos),
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
            "aircraft_icon": aircraft_icons.get(pos.pilot_id, "hang_glider") if pos.pilot_id is not None else "hang_glider",
            "profile_type": _profile_for(pos),
            "position_source": normalize_position_source(pos.source),
        }
        for pos in rows
    ]


def get_position_history_for_pilots(
    session: Session,
    pilot_ids: list[int],
    *,
    since: datetime | None = None,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    """Return position history for a set of pilots (all tasks + free-flight)."""
    if not pilot_ids:
        return []

    query = select(LivePosition).where(LivePosition.pilot_id.in_(pilot_ids))
    if since is not None:
        query = query.where(LivePosition.timestamp >= since)
    query = query.order_by(LivePosition.timestamp.asc()).limit(limit)

    rows = session.scalars(query).all()
    aircraft_icons = _aircraft_icons_by_pilot(session, pilot_ids)
    profile_types = _profile_types_by_pilot(session, pilot_ids)
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
            "aircraft_icon": aircraft_icons.get(pos.pilot_id, "hang_glider"),
            "profile_type": profile_types.get(pos.pilot_id, "pilot"),
            "position_source": normalize_position_source(pos.source),
        }
        for pos in rows
    ]
