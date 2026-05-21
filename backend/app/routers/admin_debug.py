"""Admin debug status endpoint for live tracking diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_admin
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, SosAlert, Task, TrackingSession, User
from app.services.mesh_ids import (
    mesh_device_id_lookup_variants,
    normalize_mesh_device_id,
    resolve_mesh_device_display_names,
)

router = APIRouter(tags=["admin-debug"])

MESH_STATUS_LIVE_SECONDS = 10 * 60
MESH_STATUS_STALE_SECONDS = 6 * 60 * 60


def _age_seconds(now: datetime, value: datetime | None) -> float | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return (now - value).total_seconds()


def _timestamp_value(value: datetime | None) -> float:
    if value is None:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _is_recent(now: datetime, value: datetime | None, *, seconds: int = 60) -> bool:
    age = _age_seconds(now, value)
    return age is not None and age < seconds


def mesh_status_for_seen_at(now: datetime, value: datetime | None) -> str:
    age = _age_seconds(now, value)
    if age is None:
        return "never_seen"
    if age < MESH_STATUS_LIVE_SECONDS:
        return "live"
    if age < MESH_STATUS_STALE_SECONDS:
        return "stale"
    return "offline"


@router.get("/api/admin/debug/status")
def admin_debug_status(
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> dict:
    """Return a comprehensive debug snapshot of the live tracking system."""

    # ---- MQTT status --------------------------------------------------------
    try:
        from app.services.mqtt_subscriber import mqtt_connected, mqtt_last_message_at
    except ImportError:
        mqtt_connected = False
        mqtt_last_message_at = None

    # ---- SSE subscriber counts ----------------------------------------------
    try:
        from app.services.tracking import _subscribers
    except ImportError:
        _subscribers = {}

    sse_subscribers_by_task: dict[str, int] = {
        str(task_id): len(subs) for task_id, subs in _subscribers.items()
    }
    sse_subscriber_count = sum(len(subs) for subs in _subscribers.values())

    # ---- Active sessions with pilot/task names and latest position ----------
    active_sessions_rows = session.execute(
        select(
            TrackingSession,
            Pilot.first_name,
            Pilot.last_name,
            Task.name.label("task_name"),
        )
        .outerjoin(Pilot, TrackingSession.pilot_id == Pilot.id)
        .outerjoin(Task, TrackingSession.task_id == Task.id)
        .where(TrackingSession.is_active.is_(True))
        .order_by(TrackingSession.last_seen_at.desc())
    ).all()

    now = datetime.now(UTC)
    sixty_seconds_ago = now - timedelta(seconds=60)

    active_sessions = []
    for ts, first_name, last_name, task_name in active_sessions_rows:
        pilot_name = f"{first_name or ''} {last_name or ''}".strip() or "Unknown"

        # Latest position for this session's pilot (any task including free-flight)
        pos_filter = [LivePosition.pilot_id == ts.pilot_id]
        if ts.task_id is not None:
            pos_filter.append(LivePosition.task_id == ts.task_id)
        else:
            pos_filter.append(LivePosition.task_id.is_(None))

        latest_pos = session.scalar(
            select(LivePosition)
            .where(*pos_filter)
            .order_by(LivePosition.timestamp.desc())
            .limit(1)
        )

        # Count positions in last 60 seconds
        positions_last_60s = session.scalar(
            select(func.count())
            .select_from(LivePosition)
            .where(
                *pos_filter,
                LivePosition.timestamp >= sixty_seconds_ago,
            )
        ) or 0

        # Check for any mesh-sourced positions from this pilot (ever)
        has_mesh = session.scalar(
            select(func.count())
            .select_from(LivePosition)
            .where(
                LivePosition.pilot_id == ts.pilot_id,
                LivePosition.source.in_(["mqtt_gateway", "mesh_relay"]),
            )
        ) or 0

        last_position = None
        device_id = None
        source = None
        battery_level = None
        if latest_pos is not None:
            last_position = {
                "lat": latest_pos.lat,
                "lon": latest_pos.lon,
                "alt": latest_pos.alt,
                "speed": latest_pos.speed,
            }
            device_id = latest_pos.device_id
            source = latest_pos.source
            battery_level = latest_pos.battery_level

        # Online = received a position in the last 60 seconds
        is_online = _is_recent(now, ts.last_seen_at)

        active_sessions.append({
            "pilot_id": ts.pilot_id,
            "pilot_name": pilot_name,
            "task_id": ts.task_id,
            "task_name": task_name or ("Free Flight" if ts.task_id is None else None),
            "device_id": device_id,
            "source": source,
            "battery_level": battery_level,
            "position_count": ts.position_count or 0,
            "positions_last_60s": positions_last_60s,
            "started_at": ts.started_at.isoformat() if ts.started_at else None,
            "last_seen_at": ts.last_seen_at.isoformat() if ts.last_seen_at else None,
            "last_position": last_position,
            "is_online": is_online,
            "has_mesh": has_mesh > 0,
        })

    # ---- Registered Meshtastic devices --------------------------------------
    registered_device_rows = session.execute(
        select(
            MeshDevice,
            User.id.label("owner_user_id"),
            User.full_name.label("owner_name"),
            User.pilot_id.label("owner_pilot_id"),
        )
        .join(User, MeshDevice.owner_user_id == User.id)
        .order_by(User.full_name.asc(), MeshDevice.purpose.asc(), MeshDevice.label.asc(), MeshDevice.device_id.asc())
    ).all()

    registered_device_ids = [device.device_id for device, *_ in registered_device_rows]
    registered_device_lookup_ids = sorted(
        {
            candidate
            for device_id in registered_device_ids
            for candidate in mesh_device_id_lookup_variants(device_id)
        }
    )
    latest_by_device: dict[str, object] = {}
    status_by_device: dict[str, MeshNodeStatus] = {}
    if registered_device_lookup_ids:
        row_num = func.row_number().over(
            partition_by=LivePosition.device_id,
            order_by=LivePosition.timestamp.desc(),
        ).label("rn")
        latest_subq = (
            select(LivePosition, row_num)
            .where(LivePosition.device_id.in_(registered_device_lookup_ids))
            .subquery()
        )
        latest_rows = session.execute(select(latest_subq).where(latest_subq.c.rn == 1)).all()
        latest_by_device = {row.device_id: row for row in latest_rows if row.device_id}
        statuses = session.scalars(
            select(MeshNodeStatus).where(MeshNodeStatus.device_id.in_(registered_device_lookup_ids))
        ).all()
        status_by_device = {status.device_id: status for status in statuses}
    gateway_display_names = resolve_mesh_device_display_names(
        session,
        {status.last_gateway_id for status in status_by_device.values()},
    )

    registered_mesh_devices = []
    for device, owner_user_id, owner_name, owner_pilot_id in registered_device_rows:
        lookup_ids = mesh_device_id_lookup_variants(device.device_id)
        canonical_device_id = normalize_mesh_device_id(device.device_id) or device.device_id
        latest_pos = next((latest_by_device[lookup_id] for lookup_id in lookup_ids if lookup_id in latest_by_device), None)
        node_status = next((status_by_device[lookup_id] for lookup_id in lookup_ids if lookup_id in status_by_device), None)
        status_ts = node_status.last_seen_at if node_status is not None else None
        latest_pos_ts = getattr(latest_pos, "timestamp", None)
        latest_ts = status_ts
        if latest_pos_ts is not None and _timestamp_value(latest_pos_ts) > _timestamp_value(latest_ts):
            latest_ts = latest_pos_ts
        mesh_status = mesh_status_for_seen_at(now, latest_ts)
        registered_mesh_devices.append({
            "owner_user_id": owner_user_id,
            "owner_name": owner_name,
            "owner_pilot_id": owner_pilot_id,
            "device_id": canonical_device_id,
            "label": device.label,
            "purpose": device.purpose,
            "is_active": device.is_active,
            "is_connected": mesh_status == "live",
            "mesh_status": mesh_status,
            "last_seen_at": latest_ts.isoformat() if latest_ts else None,
            "last_packet_type": node_status.last_packet_type if node_status is not None else ("POSITION_APP" if latest_pos is not None else None),
            "last_gateway_id": node_status.last_gateway_id if node_status is not None else None,
            "last_gateway_display_name": (
                gateway_display_names.get(node_status.last_gateway_id)
                if node_status is not None and node_status.last_gateway_id is not None
                else None
            ),
            "last_topic": node_status.last_topic if node_status is not None else None,
            "packet_count": node_status.packet_count if node_status is not None else (1 if latest_pos is not None else 0),
            "long_name": node_status.long_name if node_status is not None else None,
            "short_name": node_status.short_name if node_status is not None else None,
            "battery_level": (
                node_status.battery_level
                if node_status is not None and node_status.battery_level is not None
                else getattr(latest_pos, "battery_level", None) if latest_pos is not None else None
            ),
            "source": (
                node_status.last_source
                if node_status is not None and node_status.last_source is not None
                else getattr(latest_pos, "source", None) if latest_pos is not None else None
            ),
            "last_position": (
                {
                    "lat": latest_pos.lat,
                    "lon": latest_pos.lon,
                    "alt": latest_pos.alt,
                    "speed": latest_pos.speed,
                    "heading": latest_pos.heading,
                }
                if latest_pos is not None
                else None
            ),
        })

    # ---- Recent SOS alerts --------------------------------------------------
    sos_rows = session.execute(
        select(
            SosAlert,
            Pilot.first_name,
            Pilot.last_name,
        )
        .outerjoin(Pilot, SosAlert.pilot_id == Pilot.id)
        .order_by(SosAlert.timestamp.desc())
        .limit(10)
    ).all()

    recent_sos_alerts = [
        {
            "pilot_id": alert.pilot_id,
            "pilot_name": f"{first_name or ''} {last_name or ''}".strip() or "Unknown",
            "lat": alert.lat,
            "lon": alert.lon,
            "alt": alert.alt,
            "message": alert.message,
            "timestamp": alert.timestamp.isoformat(),
        }
        for alert, first_name, last_name in sos_rows
    ]

    # ---- Position stats (last hour) -----------------------------------------
    one_hour_ago = now - timedelta(hours=1)

    last_hour_total = session.scalar(
        select(func.count())
        .select_from(LivePosition)
        .where(LivePosition.timestamp >= one_hour_ago)
    ) or 0

    source_counts = session.execute(
        select(LivePosition.source, func.count())
        .where(LivePosition.timestamp >= one_hour_ago)
        .group_by(LivePosition.source)
    ).all()

    source_map: dict[str | None, int] = {src: cnt for src, cnt in source_counts}
    last_hour_cellular = source_map.get("app", 0)
    last_hour_mesh = source_map.get("mqtt_gateway", 0) + source_map.get("mesh_relay", 0)

    return {
        "mqtt_connected": mqtt_connected,
        "mqtt_last_message_at": mqtt_last_message_at.isoformat() if mqtt_last_message_at else None,
        "sse_subscriber_count": sse_subscriber_count,
        "sse_subscribers_by_task": sse_subscribers_by_task,
        "active_sessions": active_sessions,
        "registered_mesh_devices": registered_mesh_devices,
        "recent_sos_alerts": recent_sos_alerts,
        "position_stats": {
            "last_hour_total": last_hour_total,
            "last_hour_cellular": last_hour_cellular,
            "last_hour_mesh": last_hour_mesh,
        },
    }
