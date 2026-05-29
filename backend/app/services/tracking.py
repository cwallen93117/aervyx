from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, not_, or_, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import DriverAssignment, Event, EventPilot, LivePosition, MeshDevice, Task, TrackingSession, User
from app.services.mesh_ids import mesh_device_id_lookup_variants, normalize_mesh_device_id


# ---------------------------------------------------------------------------
# Internal asyncio pub/sub for SSE fan-out
# ---------------------------------------------------------------------------

class LiveSubscriber:
    def __init__(self, *, maxsize: int = 256) -> None:
        self.loop = asyncio.get_running_loop()
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=maxsize)

    async def get(self) -> dict[str, Any]:
        return await self.queue.get()

    def enqueue(self, message: dict[str, Any]) -> bool:
        if self.loop.is_closed():
            return False
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is self.loop:
            return self._put_nowait(message)
        try:
            self.loop.call_soon_threadsafe(self._put_nowait, message)
        except RuntimeError:
            return False
        return True

    def _put_nowait(self, message: dict[str, Any]) -> bool:
        try:
            self.queue.put_nowait(dict(message))
        except asyncio.QueueFull:
            return False
        except Exception:
            logger.warning("Dropping failed live-tracking subscriber", exc_info=True)
            return False
        return True


_subscribers: dict[int, set[LiveSubscriber]] = {}
_pilot_subscribers: dict[int, set[LiveSubscriber]] = {}
_user_subscribers: dict[int, set[LiveSubscriber]] = {}
_global_subscribers: set[LiveSubscriber] = set()
_subscriber_lock = threading.RLock()
logger = logging.getLogger("aervyx.tracking")
VALID_AIRCRAFT_ICONS = {"hang_glider", "paraglider", "sailplane"}
VALID_PROFILE_TYPES_ALL = {"pilot", "driver", "stationary_node"}
TRACKING_MESH_PURPOSE = "tracking"
DRIVER_MESH_PURPOSES = {"driver_wifi", "driver_mesh"}
STATIONARY_MESH_PURPOSES = {"base_station", "relay"}
LIVE_POSITION_PRUNE_INTERVAL_SECONDS = 300
TIMEZONE_ALIASES = {
    "eastern": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "us/eastern": "America/New_York",
    "central": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "us/central": "America/Chicago",
    "mountain": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "us/mountain": "America/Denver",
    "pacific": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "us/pacific": "America/Los_Angeles",
    "utc": "UTC",
}


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _max_datetime(left: datetime | None, right: datetime | None) -> datetime:
    if left is None:
        return _as_utc(right)
    if right is None:
        return _as_utc(left)
    return left if _as_utc(left) >= _as_utc(right) else right


def _iso_or_none(value: datetime | None) -> str | None:
    return _as_utc(value).isoformat() if value is not None else None


def resolve_tracking_timezone_name(value: str | None) -> str:
    if not value:
        return "UTC"
    normalized = value.strip()
    candidate = TIMEZONE_ALIASES.get(normalized.lower(), normalized)
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid live tracking timezone %r; falling back to UTC", value)
        return "UTC"
    return candidate


def _current_day_window_utc(timezone_name: str, now: datetime | None = None) -> tuple[datetime, datetime]:
    zone_name = resolve_tracking_timezone_name(timezone_name)
    zone = ZoneInfo(zone_name)
    local_now = _as_utc(now).astimezone(zone)
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    local_end = local_start + timedelta(days=1)
    return local_start.astimezone(UTC), local_end.astimezone(UTC)


def _event_timezone_groups(session: Session) -> dict[str, list[str | None]]:
    rows = session.scalars(select(Event.timezone).distinct()).all()
    groups: dict[str, list[str | None]] = {}
    for raw_timezone in rows:
        groups.setdefault(resolve_tracking_timezone_name(raw_timezone), []).append(raw_timezone)
    return groups


def _task_ids_for_raw_timezones(raw_timezones: list[str | None]):
    conditions = []
    values = [value for value in raw_timezones if value is not None]
    if values:
        conditions.append(Event.timezone.in_(values))
    if any(value is None for value in raw_timezones):
        conditions.append(Event.timezone.is_(None))
    if not conditions:
        return select(Task.id).where(False)
    return select(Task.id).join(Event, Task.event_id == Event.id).where(or_(*conditions))


def _current_day_position_clause(session: Session, *, now: datetime | None = None):
    reference_time = _as_utc(now)
    conditions = []

    for timezone_name, raw_timezones in _event_timezone_groups(session).items():
        start_utc, end_utc = _current_day_window_utc(timezone_name, reference_time)
        task_ids = _task_ids_for_raw_timezones(raw_timezones)
        conditions.append(
            and_(
                LivePosition.task_id.isnot(None),
                LivePosition.task_id.in_(task_ids),
                LivePosition.timestamp >= start_utc,
                LivePosition.timestamp < end_utc,
            )
        )

    utc_start, utc_end = _current_day_window_utc("UTC", reference_time)
    known_event_task_ids = select(Task.id).join(Event, Task.event_id == Event.id)
    conditions.append(
        and_(
            or_(
                LivePosition.task_id.is_(None),
                not_(LivePosition.task_id.in_(known_event_task_ids)),
            ),
            LivePosition.timestamp >= utc_start,
            LivePosition.timestamp < utc_end,
        )
    )

    return or_(*conditions)


def _optional_since(since: datetime | None, minutes: int | None, now: datetime | None) -> datetime | None:
    cutoffs = []
    if since is not None:
        cutoffs.append(_as_utc(since))
    if minutes is not None:
        cutoffs.append(_as_utc(now) - timedelta(minutes=minutes))
    return max(cutoffs) if cutoffs else None


def _apply_live_position_history_window(
    session: Session,
    query,
    *,
    since: datetime | None = None,
    minutes: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
):
    reference_time = _as_utc(now)
    query = query.where(_current_day_position_clause(session, now=reference_time))
    since_cutoff = _optional_since(since, minutes, reference_time)
    if since_cutoff is not None:
        query = query.where(LivePosition.timestamp >= since_cutoff)
    if limit is not None:
        query = query.limit(limit)
    return query


def prune_old_live_positions(
    retention_days: int | None = None,
    *,
    now: datetime | None = None,
) -> int:
    """Delete live tracking fixes outside the current day for their event timezone."""
    reference_time = _as_utc(now)
    if retention_days is not None:
        logger.debug("Ignoring deprecated live-position retention_days=%s; using current-day retention", retention_days)

    session = SessionLocal()
    try:
        deleted = (
            session.query(LivePosition)
            .filter(not_(_current_day_position_clause(session, now=reference_time)))
            .delete(synchronize_session=False)
        )
        session.commit()
        if deleted:
            logger.info("Pruned %d live positions outside the current local day", deleted)
        return int(deleted)
    except Exception:
        session.rollback()
        logger.warning("Failed to prune old live positions", exc_info=True)
        return 0
    finally:
        session.close()


async def _live_position_prune_loop(
    interval_seconds: int = LIVE_POSITION_PRUNE_INTERVAL_SECONDS,
) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await asyncio.to_thread(prune_old_live_positions)


async def start_live_position_pruner() -> asyncio.Task[None]:
    """Launch the live-position retention pruner as an asyncio background task."""
    task = asyncio.create_task(_live_position_prune_loop(), name="live-position-pruner")
    logger.info(
        "Live position pruner started: retention=current local day interval=%d seconds",
        LIVE_POSITION_PRUNE_INTERVAL_SECONDS,
    )
    return task


def _normalize_aircraft_icon(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    return candidate if candidate in VALID_AIRCRAFT_ICONS else "hang_glider"


def _normalize_profile_type(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    return candidate if candidate in VALID_PROFILE_TYPES_ALL else "pilot"


def mesh_purpose_to_profile_type(purpose: str | None) -> str:
    candidate = (purpose or "").strip().lower()
    if candidate in DRIVER_MESH_PURPOSES:
        return "driver"
    if candidate in STATIONARY_MESH_PURPOSES:
        return "stationary_node"
    return "pilot"


def resolve_active_task_id(session: Session, pilot_id: int | None) -> int | None:
    if pilot_id is None:
        return None
    task = session.execute(
        select(Task)
        .join(Event, Task.event_id == Event.id)
        .join(EventPilot, EventPilot.event_id == Event.id)
        .where(
            EventPilot.pilot_id == pilot_id,
            Task.status == "active",
        )
        .order_by(Task.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    return task.id if task else None


def resolve_active_task_id_for_user(session: Session, user: User | None) -> int | None:
    """Resolve the active task relevant to a user.

    Pilot profiles use event participation. Driver profiles first use explicit
    driver assignments, then fall back to the newest active task so a driver can
    still publish a vehicle position before assignments are configured.
    """
    if user is None:
        return None
    profile_type = _normalize_profile_type(user.profile_type)
    if profile_type == "driver":
        assigned_task = session.execute(
            select(Task)
            .join(DriverAssignment, DriverAssignment.task_id == Task.id)
            .where(
                DriverAssignment.driver_user_id == user.id,
                Task.status == "active",
            )
            .order_by(Task.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        if assigned_task is not None:
            return assigned_task.id
        fallback = session.scalar(
            select(Task)
            .where(Task.status == "active")
            .order_by(Task.id.desc())
            .limit(1)
        )
        return fallback.id if fallback is not None else None
    return resolve_active_task_id(session, user.pilot_id)


def resolve_mesh_device_assignment(session: Session, device_id: str | None) -> tuple[User | None, MeshDevice | None]:
    normalized = normalize_mesh_device_id(device_id)
    if not normalized:
        return None, None

    device = None
    for candidate in mesh_device_id_lookup_variants(normalized):
        device = session.scalar(
            select(MeshDevice).where(MeshDevice.device_id == candidate)
        )
        if device is not None:
            break
    if device is not None:
        owner = session.get(User, device.owner_user_id)
        owner_tracker_ids = set(mesh_device_id_lookup_variants(owner.mesh_device_id if owner else None))
        if (
            device.purpose != TRACKING_MESH_PURPOSE
            or normalized not in owner_tracker_ids
            or owner is None
            or not owner.is_active
        ):
            return None, device
        return owner, device

    legacy_owner = None
    for candidate in mesh_device_id_lookup_variants(normalized):
        legacy_owner = session.scalar(
            select(User).where(
                User.mesh_device_id == candidate,
                User.is_active.is_(True),
            )
        )
        if legacy_owner is not None:
            break
    return legacy_owner, None


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
    if candidate in ("mqtt_gateway", "mesh_relay"):
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


def _pilot_names_by_pilot(session: Session, pilot_ids: list[int]) -> dict[int, str]:
    if not pilot_ids:
        return {}
    users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids)).order_by(User.id.asc())).all()
    pilot_names: dict[int, str] = {}
    for user in users:
        if user.pilot_id is not None and user.pilot_id not in pilot_names:
            pilot_names[user.pilot_id] = user.full_name
    return pilot_names


def _users_by_id(session: Session, user_ids: list[int]) -> dict[int, User]:
    if not user_ids:
        return {}
    users = session.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.id.asc())).all()
    return {user.id: user for user in users}


def _users_by_pilot_id(session: Session, pilot_ids: list[int]) -> dict[int, User]:
    if not pilot_ids:
        return {}
    users = session.scalars(select(User).where(User.pilot_id.in_(pilot_ids)).order_by(User.id.asc())).all()
    by_pilot: dict[int, User] = {}
    for user in users:
        if user.pilot_id is not None and user.pilot_id not in by_pilot:
            by_pilot[user.pilot_id] = user
    return by_pilot


def _registered_devices_by_device_id(session: Session, device_ids: list[str]) -> dict[str, MeshDevice]:
    lookup_ids: set[str] = set()
    for device_id in device_ids:
        normalized = normalize_mesh_device_id(device_id)
        if not normalized:
            continue
        lookup_ids.update(mesh_device_id_lookup_variants(normalized))
    if not lookup_ids:
        return {}
    devices = session.scalars(
        select(MeshDevice).where(MeshDevice.device_id.in_(lookup_ids))
    ).all()
    by_id: dict[str, MeshDevice] = {}
    for device in devices:
        normalized = normalize_mesh_device_id(device.device_id)
        candidates = {device.device_id}
        if normalized:
            candidates.update(mesh_device_id_lookup_variants(normalized))
        for candidate in candidates:
            by_id[candidate] = device
    return by_id


def subject_key_for_position(pos: LivePosition, *, profile_type: str = "pilot") -> str:
    if pos.user_id is not None and _normalize_profile_type(profile_type) == "driver":
        return f"user:{pos.user_id}"
    if pos.pilot_id is not None:
        return f"pilot:{pos.pilot_id}"
    if pos.user_id is not None:
        return f"user:{pos.user_id}"
    normalized_device = normalize_mesh_device_id(pos.device_id)
    if normalized_device:
        return f"device:{normalized_device}"
    return f"position:{pos.id}"


def _position_payload(
    pos: LivePosition,
    *,
    users_by_id: dict[int, User],
    users_by_pilot: dict[int, User],
    devices_by_id: dict[str, MeshDevice] | None = None,
) -> dict[str, Any]:
    user = users_by_id.get(pos.user_id) if pos.user_id is not None else None
    pilot_user = users_by_pilot.get(pos.pilot_id) if pos.pilot_id is not None else None
    profile_user = user or pilot_user
    profile_type = _normalize_profile_type(profile_user.profile_type) if profile_user is not None else "pilot"
    aircraft_icon = _normalize_aircraft_icon(profile_user.aircraft_icon) if profile_user is not None else "hang_glider"
    pilot_name = profile_user.full_name if profile_user is not None else None

    device = None
    if devices_by_id is not None and pos.device_id:
        device = devices_by_id.get(pos.device_id)
        normalized_device = normalize_mesh_device_id(pos.device_id)
        if device is None and normalized_device:
            for candidate in mesh_device_id_lookup_variants(normalized_device):
                device = devices_by_id.get(candidate)
                if device is not None:
                    break
    if device is not None and pos.pilot_id is None and pos.user_id is None:
        profile_type = mesh_purpose_to_profile_type(device.purpose)
        pilot_name = device.label

    return {
        "id": str(pos.id),
        "subject_key": subject_key_for_position(pos, profile_type=profile_type),
        "pilot_id": pos.pilot_id,
        "user_id": pos.user_id,
        "pilot_name": pilot_name,
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
        "aircraft_icon": aircraft_icon,
        "profile_type": profile_type,
        "position_source": normalize_position_source(pos.source),
        "received_at": _iso_or_none(pos.created_at),
    }


def _payload_context(session: Session, rows: list[LivePosition]) -> tuple[dict[int, User], dict[int, User], dict[str, MeshDevice]]:
    user_ids = sorted({pos.user_id for pos in rows if pos.user_id is not None})
    pilot_ids = sorted({pos.pilot_id for pos in rows if pos.pilot_id is not None})
    device_ids = sorted({pos.device_id for pos in rows if pos.device_id})
    return (
        _users_by_id(session, user_ids),
        _users_by_pilot_id(session, pilot_ids),
        _registered_devices_by_device_id(session, device_ids),
    )


def _payloads_for_positions(session: Session, rows: list[LivePosition]) -> list[dict[str, Any]]:
    users_by_id, users_by_pilot, devices_by_id = _payload_context(session, rows)
    return [
        _position_payload(
            pos,
            users_by_id=users_by_id,
            users_by_pilot=users_by_pilot,
            devices_by_id=devices_by_id,
        )
        for pos in rows
    ]


def _latest_payloads_by_subject(session: Session, rows: list[LivePosition]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for payload in _payloads_for_positions(session, rows):
        subject_key = payload["subject_key"]
        previous = latest.get(subject_key)
        if previous is None or payload["timestamp"] > previous["timestamp"]:
            latest[subject_key] = payload
    return sorted(latest.values(), key=lambda payload: payload["timestamp"], reverse=True)


def _stationary_node_by_device(session: Session, device_ids: list[str]) -> dict[str, User]:
    """Return a map of ``device_id → User`` for any stationary-node users matching the given device IDs."""
    if not device_ids:
        return {}
    lookup_ids: set[str] = set()
    canonical_by_lookup: dict[str, str] = {}
    for device_id in device_ids:
        normalized = normalize_mesh_device_id(device_id)
        if not normalized:
            continue
        for candidate in mesh_device_id_lookup_variants(normalized):
            lookup_ids.add(candidate)
            canonical_by_lookup[candidate] = normalized
    if not lookup_ids:
        return {}
    users = session.scalars(
        select(User).where(
            User.mesh_device_id.in_(lookup_ids),
            User.profile_type == "stationary_node",
        )
    ).all()
    return {canonical_by_lookup.get(user.mesh_device_id, user.mesh_device_id): user for user in users if user.mesh_device_id}


def subscribe(task_id: int) -> LiveSubscriber:
    """Register a new SSE subscriber for a given task. Returns a queue."""
    subscriber = LiveSubscriber(maxsize=256)
    with _subscriber_lock:
        _subscribers.setdefault(task_id, set()).add(subscriber)
    return subscriber


def unsubscribe(task_id: int, subscriber: LiveSubscriber) -> None:
    """Remove a subscriber queue for a given task."""
    with _subscriber_lock:
        task_subs = _subscribers.get(task_id)
        if task_subs:
            task_subs.discard(subscriber)
            if not task_subs:
                del _subscribers[task_id]


def _publish(task_id: int, message: dict[str, Any]) -> None:
    """Fan out a message to all SSE subscribers for a task (non-blocking)."""
    with _subscriber_lock:
        task_subs = _subscribers.get(task_id)
        targets = list(task_subs) if task_subs else []
    if not targets:
        return
    dead: list[LiveSubscriber] = []
    for subscriber in targets:
        if not subscriber.enqueue(message):
            dead.append(subscriber)
    if dead:
        with _subscriber_lock:
            task_subs = _subscribers.get(task_id)
            if task_subs:
                for subscriber in dead:
                    task_subs.discard(subscriber)
                if not task_subs:
                    del _subscribers[task_id]


# ---------------------------------------------------------------------------
# Pilot-scoped pub/sub (for buddy group tracking)
# ---------------------------------------------------------------------------

def subscribe_pilots(pilot_ids: list[int]) -> LiveSubscriber:
    """Register a single queue that receives positions for any of the given pilot IDs."""
    subscriber = LiveSubscriber(maxsize=256)
    with _subscriber_lock:
        for pid in pilot_ids:
            _pilot_subscribers.setdefault(pid, set()).add(subscriber)
    return subscriber


def unsubscribe_pilots(pilot_ids: list[int], subscriber: LiveSubscriber) -> None:
    """Remove a subscriber queue from all specified pilot channels."""
    with _subscriber_lock:
        for pid in pilot_ids:
            subs = _pilot_subscribers.get(pid)
            if subs:
                subs.discard(subscriber)
                if not subs:
                    del _pilot_subscribers[pid]


def _publish_to_pilot_subscribers(pilot_id: int, message: dict[str, Any]) -> None:
    """Fan out a message to all SSE subscribers watching a specific pilot."""
    with _subscriber_lock:
        subs = _pilot_subscribers.get(pilot_id)
        targets = list(subs) if subs else []
    if not targets:
        return
    dead: list[LiveSubscriber] = []
    for subscriber in targets:
        if not subscriber.enqueue(message):
            dead.append(subscriber)
    if dead:
        with _subscriber_lock:
            subs = _pilot_subscribers.get(pilot_id)
            if subs:
                for subscriber in dead:
                    subs.discard(subscriber)
                if not subs:
                    del _pilot_subscribers[pilot_id]


# ---------------------------------------------------------------------------
# Global pub/sub (debug mode — broadcasts every position to every subscriber)
# ---------------------------------------------------------------------------

def subscribe_users(user_ids: list[int]) -> LiveSubscriber:
    """Register a single queue that receives positions for any of the given user IDs."""
    subscriber = LiveSubscriber(maxsize=256)
    with _subscriber_lock:
        for uid in user_ids:
            _user_subscribers.setdefault(uid, set()).add(subscriber)
    return subscriber


def unsubscribe_users(user_ids: list[int], subscriber: LiveSubscriber) -> None:
    """Remove a subscriber queue from all specified user channels."""
    with _subscriber_lock:
        for uid in user_ids:
            subs = _user_subscribers.get(uid)
            if subs:
                subs.discard(subscriber)
                if not subs:
                    del _user_subscribers[uid]


def subscribe_subjects(pilot_ids: list[int], user_ids: list[int]) -> LiveSubscriber:
    """Register one queue for a mix of pilot- and user-scoped subjects."""
    subscriber = LiveSubscriber(maxsize=512)
    with _subscriber_lock:
        for pid in pilot_ids:
            _pilot_subscribers.setdefault(pid, set()).add(subscriber)
        for uid in user_ids:
            _user_subscribers.setdefault(uid, set()).add(subscriber)
    return subscriber


def unsubscribe_subjects(pilot_ids: list[int], user_ids: list[int], subscriber: LiveSubscriber) -> None:
    with _subscriber_lock:
        for pid in pilot_ids:
            subs = _pilot_subscribers.get(pid)
            if subs:
                subs.discard(subscriber)
                if not subs:
                    del _pilot_subscribers[pid]
        for uid in user_ids:
            subs = _user_subscribers.get(uid)
            if subs:
                subs.discard(subscriber)
                if not subs:
                    del _user_subscribers[uid]


def _publish_to_user_subscribers(user_id: int, message: dict[str, Any]) -> None:
    """Fan out a message to all SSE subscribers watching a specific user."""
    with _subscriber_lock:
        subs = _user_subscribers.get(user_id)
        targets = list(subs) if subs else []
    if not targets:
        return
    dead: list[LiveSubscriber] = []
    for subscriber in targets:
        if not subscriber.enqueue(message):
            dead.append(subscriber)
    if dead:
        with _subscriber_lock:
            subs = _user_subscribers.get(user_id)
            if subs:
                for subscriber in dead:
                    subs.discard(subscriber)
                if not subs:
                    del _user_subscribers[user_id]


def subscribe_global() -> LiveSubscriber:
    """Register a new SSE subscriber that receives EVERY incoming position."""
    subscriber = LiveSubscriber(maxsize=512)
    with _subscriber_lock:
        _global_subscribers.add(subscriber)
    return subscriber


def unsubscribe_global(subscriber: LiveSubscriber) -> None:
    """Remove a global SSE subscriber queue."""
    with _subscriber_lock:
        _global_subscribers.discard(subscriber)


def _publish_global(message: dict[str, Any]) -> None:
    """Fan out a message to all global SSE subscribers."""
    with _subscriber_lock:
        targets = list(_global_subscribers)
    if not targets:
        return
    dead: list[LiveSubscriber] = []
    for subscriber in targets:
        if not subscriber.enqueue(message):
            dead.append(subscriber)
    if dead:
        with _subscriber_lock:
            for subscriber in dead:
                _global_subscribers.discard(subscriber)


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
    battery_level_seen_at: datetime | None = None,
    pilot_id: int | None = None,
    user_id: int | None = None,
) -> LivePosition:
    """Persist a position fix and fan it out to SSE subscribers."""
    ts = timestamp or datetime.now(UTC)
    pos = LivePosition(
        id=uuid.uuid4(),
        pilot_id=pilot_id,
        user_id=user_id,
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
        battery_level_seen_at=battery_level_seen_at,
    )
    session.add(pos)

    # Upsert tracking session (for all positions, including free-flight). Use a
    # pilot subject when available; otherwise use the user subject for drivers.
    if pilot_id is not None or user_id is not None:
        filters = [TrackingSession.is_active.is_(True)]
        if task_id is None:
            filters.append(TrackingSession.task_id.is_(None))
        else:
            filters.append(TrackingSession.task_id == task_id)
        if pilot_id is not None:
            filters.append(TrackingSession.pilot_id == pilot_id)
        else:
            filters.append(TrackingSession.pilot_id.is_(None))
            filters.append(TrackingSession.user_id == user_id)
        tracking = session.scalar(select(TrackingSession).where(*filters))

        if tracking is not None:
            tracking.last_seen_at = _max_datetime(tracking.last_seen_at, ts)
            tracking.position_count = (tracking.position_count or 0) + 1
        else:
            tracking = TrackingSession(
                id=uuid.uuid4(),
                pilot_id=pilot_id,
                user_id=user_id,
                task_id=task_id,
                started_at=ts,
                last_seen_at=ts,
                is_active=True,
                position_count=1,
            )
            session.add(tracking)

    session.flush()

    # Build SSE message once for all fan-out paths -----------------------------
    with _subscriber_lock:
        has_any_subscribers = (
            (task_id is not None and task_id in _subscribers)
            or (pilot_id is not None and pilot_id in _pilot_subscribers)
            or (user_id is not None and user_id in _user_subscribers)
            or bool(_global_subscribers)
        )
    if has_any_subscribers:
        users_by_id, users_by_pilot, devices_by_id = _payload_context(session, [pos])
        message = _position_payload(
            pos,
            users_by_id=users_by_id,
            users_by_pilot=users_by_pilot,
            devices_by_id=devices_by_id,
        )
        if task_id is not None:
            _publish(task_id, message)
        if pilot_id is not None:
            _publish_to_pilot_subscribers(pilot_id, message)
        if user_id is not None:
            _publish_to_user_subscribers(user_id, message)
        _publish_global(message)

    # Server-side landing detection
    if pilot_id is not None and task_id is not None:
        try:
            from app.services.routing.landing_detector import check_landing

            landing_event = check_landing(
                session,
                task_id=task_id,
                pilot_id=pilot_id,
                lat=pos.lat,
                lon=pos.lon,
                alt=pos.alt,
                speed=pos.speed,
                timestamp=ts,
            )
            if landing_event is not None and task_id in _subscribers:
                _publish(task_id, landing_event)
        except Exception:
            logging.getLogger(__name__).debug("Landing detection error", exc_info=True)

    return pos


def get_live_positions(session: Session, task_id: int) -> list[dict[str, Any]]:
    """Return the latest retained current-day position per live subject for a task."""
    active_sessions = session.scalars(
        select(TrackingSession).where(
            TrackingSession.task_id == task_id,
            TrackingSession.is_active.is_(True),
        )
    ).all()

    if not active_sessions:
        return []

    pilot_ids = sorted({s.pilot_id for s in active_sessions if s.pilot_id is not None})
    user_ids = sorted({s.user_id for s in active_sessions if s.pilot_id is None and s.user_id is not None})
    conditions = []
    if pilot_ids:
        conditions.append(LivePosition.pilot_id.in_(pilot_ids))
    if user_ids:
        conditions.append(LivePosition.user_id.in_(user_ids))
    if not conditions:
        return []

    rows = session.scalars(
        select(LivePosition)
        .where(LivePosition.task_id == task_id, or_(*conditions), _current_day_position_clause(session))
        .order_by(LivePosition.timestamp.desc())
        .limit(max(1000, len(conditions) * 100))
    ).all()

    return _latest_payloads_by_subject(session, rows)


def get_all_active_positions(session: Session, minutes: int = 5) -> list[dict[str, Any]]:
    """Return latest retained current-day position for every active live subject."""
    active_sessions = session.scalars(
        select(TrackingSession).where(
            TrackingSession.is_active.is_(True),
        )
    ).all()

    if not active_sessions:
        return []

    pilot_ids = sorted({s.pilot_id for s in active_sessions if s.pilot_id is not None})
    user_ids = sorted({s.user_id for s in active_sessions if s.pilot_id is None and s.user_id is not None})
    conditions = []
    if pilot_ids:
        conditions.append(LivePosition.pilot_id.in_(pilot_ids))
    if user_ids:
        conditions.append(LivePosition.user_id.in_(user_ids))
    if not conditions:
        return []

    rows = session.scalars(
        select(LivePosition)
        .where(or_(*conditions), _current_day_position_clause(session))
        .order_by(LivePosition.timestamp.desc())
        .limit(max(1000, len(conditions) * 100))
    ).all()

    return _latest_payloads_by_subject(session, rows)


def get_position_history(
    session: Session,
    task_id: int,
    *,
    pilot_id: int | None = None,
    since: datetime | None = None,
    minutes: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return historical positions for a task, optionally filtered by pilot and time."""
    query = select(LivePosition).where(LivePosition.task_id == task_id)
    if pilot_id is not None:
        query = query.where(LivePosition.pilot_id == pilot_id)
    query = _apply_live_position_history_window(
        session,
        query,
        since=since,
        minutes=minutes,
        limit=limit,
        now=now,
    )
    query = query.order_by(LivePosition.timestamp.asc())

    rows = session.scalars(query).all()
    return _payloads_for_positions(session, rows)


# ---------------------------------------------------------------------------
# Pilot-set queries (for buddy group tracking)
# ---------------------------------------------------------------------------

def get_live_positions_for_pilots(session: Session, pilot_ids: list[int]) -> list[dict[str, Any]]:
    """Return the latest position per pilot for a set of pilot IDs."""
    if not pilot_ids:
        return []

    rows = session.scalars(
        select(LivePosition)
        .where(LivePosition.pilot_id.in_(pilot_ids), _current_day_position_clause(session))
        .order_by(LivePosition.timestamp.desc())
        .limit(max(1000, len(pilot_ids) * 100))
    ).all()

    return _latest_payloads_by_subject(session, rows)


def get_live_positions_for_subjects(
    session: Session,
    pilot_ids: list[int],
    user_ids: list[int],
) -> list[dict[str, Any]]:
    """Return the latest position for a mix of pilot and user subjects."""
    conditions = []
    if pilot_ids:
        conditions.append(LivePosition.pilot_id.in_(pilot_ids))
    if user_ids:
        conditions.append(LivePosition.user_id.in_(user_ids))
    if not conditions:
        return []

    rows = session.scalars(
        select(LivePosition)
        .where(or_(*conditions), _current_day_position_clause(session))
        .order_by(LivePosition.timestamp.desc())
        .limit(max(1000, (len(pilot_ids) + len(user_ids)) * 100))
    ).all()
    return _latest_payloads_by_subject(session, rows)


def get_all_recent_positions(
    session: Session,
    *,
    minutes: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return every retained current-day position record, optionally narrowed by minutes.

    Used by the debug "show all" live tracking view. Intended to include free-flight
    positions as well (task_id IS NULL). Returned newest-first.
    """
    query = _apply_live_position_history_window(
        session,
        select(LivePosition),
        minutes=minutes,
        limit=limit,
        now=now,
    ).order_by(LivePosition.timestamp.desc())
    rows = session.scalars(query).all()

    return _payloads_for_positions(session, rows)


def get_position_history_for_pilots(
    session: Session,
    pilot_ids: list[int],
    *,
    since: datetime | None = None,
    minutes: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return position history for a set of pilots (all tasks + free-flight)."""
    if not pilot_ids:
        return []

    query = select(LivePosition).where(LivePosition.pilot_id.in_(pilot_ids))
    query = _apply_live_position_history_window(
        session,
        query,
        since=since,
        minutes=minutes,
        limit=limit,
        now=now,
    )
    query = query.order_by(LivePosition.timestamp.asc())

    rows = session.scalars(query).all()
    return _payloads_for_positions(session, rows)


def get_position_history_for_subjects(
    session: Session,
    pilot_ids: list[int],
    user_ids: list[int],
    *,
    since: datetime | None = None,
    minutes: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return position history for a mix of pilot and user subjects."""
    conditions = []
    if pilot_ids:
        conditions.append(LivePosition.pilot_id.in_(pilot_ids))
    if user_ids:
        conditions.append(LivePosition.user_id.in_(user_ids))
    if not conditions:
        return []

    query = select(LivePosition).where(or_(*conditions))
    query = _apply_live_position_history_window(
        session,
        query,
        since=since,
        minutes=minutes,
        limit=limit,
        now=now,
    )
    query = query.order_by(LivePosition.timestamp.asc())

    rows = session.scalars(query).all()
    return _payloads_for_positions(session, rows)
