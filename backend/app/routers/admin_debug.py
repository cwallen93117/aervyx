"""Admin debug status endpoint for live tracking diagnostics."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
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
MESH_GATEWAY_METADATA_TOLERANCE_SECONDS = 5 * 60
PHONE_APP_POSITION_SOURCE = "app"


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


def _status_gateway_id_for_latest(
    node_status: MeshNodeStatus | None,
    *,
    latest_position_is_newer: bool,
    latest_position_ts: datetime | None,
    source: str | None,
    packet_type: str | None,
) -> str | None:
    if node_status is None or node_status.last_gateway_id is None:
        return None
    if not latest_position_is_newer:
        return node_status.last_gateway_id
    if latest_position_ts is None or node_status.last_seen_at is None:
        return None
    if source is not None and node_status.last_source is not None and source != node_status.last_source:
        return None
    if packet_type is not None and node_status.last_packet_type is not None and packet_type != node_status.last_packet_type:
        return None
    if (
        abs(_timestamp_value(latest_position_ts) - _timestamp_value(node_status.last_seen_at))
        <= MESH_GATEWAY_METADATA_TOLERANCE_SECONDS
    ):
        return node_status.last_gateway_id
    return None


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
            User.id.label("session_user_id"),
            User.full_name.label("session_user_name"),
            User.username.label("session_username"),
            User.profile_type.label("session_profile_type"),
            Task.name.label("task_name"),
        )
        .outerjoin(Pilot, TrackingSession.pilot_id == Pilot.id)
        .outerjoin(User, TrackingSession.user_id == User.id)
        .outerjoin(Task, TrackingSession.task_id == Task.id)
        .where(
            TrackingSession.is_active.is_(True),
            or_(TrackingSession.pilot_id.is_not(None), TrackingSession.user_id.is_not(None)),
        )
        .order_by(TrackingSession.last_seen_at.desc())
    ).all()

    now = datetime.now(UTC)
    sixty_seconds_ago = now - timedelta(seconds=60)

    active_sessions = []
    for (
        ts,
        first_name,
        last_name,
        session_user_id,
        session_user_name,
        session_username,
        session_profile_type,
        task_name,
    ) in active_sessions_rows:
        pilot_name = (
            f"{first_name or ''} {last_name or ''}".strip()
            or (session_user_name or "").strip()
            or (session_username or "").strip()
        )
        if not pilot_name:
            continue

        # Phone rows must reflect only direct app uploads. TrackingSession rows
        # are refreshed by mesh/MQTT positions too, so using the session timestamp
        # or latest position across all sources would make a mesh node look like
        # a live phone.
        pos_filter = [LivePosition.source == PHONE_APP_POSITION_SOURCE]
        if ts.pilot_id is not None:
            pos_filter.append(LivePosition.pilot_id == ts.pilot_id)
        elif ts.user_id is not None:
            pos_filter.extend([
                LivePosition.pilot_id.is_(None),
                LivePosition.user_id == ts.user_id,
            ])
        else:
            continue
        if ts.task_id is not None:
            pos_filter.append(LivePosition.task_id == ts.task_id)
        else:
            pos_filter.append(LivePosition.task_id.is_(None))

        latest_app_pos = session.scalar(
            select(LivePosition)
            .where(*pos_filter)
            .order_by(LivePosition.timestamp.desc())
            .limit(1)
        )
        if latest_app_pos is None:
            continue

        # Count phone-app positions for this session.
        phone_position_count = session.scalar(
            select(func.count())
            .select_from(LivePosition)
            .where(*pos_filter)
        ) or 0
        positions_last_60s = session.scalar(
            select(func.count())
            .select_from(LivePosition)
            .where(
                *pos_filter,
                LivePosition.timestamp >= sixty_seconds_ago,
            )
        ) or 0

        # Check for any mesh-sourced positions from this subject (ever)
        mesh_subject_filter = []
        if ts.pilot_id is not None:
            mesh_subject_filter.append(LivePosition.pilot_id == ts.pilot_id)
        elif ts.user_id is not None:
            mesh_subject_filter.extend([
                LivePosition.pilot_id.is_(None),
                LivePosition.user_id == ts.user_id,
            ])
        has_mesh = session.scalar(
            select(func.count())
            .select_from(LivePosition)
            .where(
                *mesh_subject_filter,
                LivePosition.source.in_(["mqtt_gateway", "mesh_relay"]),
            )
        ) or 0

        last_position = {
            "lat": latest_app_pos.lat,
            "lon": latest_app_pos.lon,
            "alt": latest_app_pos.alt,
            "speed": latest_app_pos.speed,
        }

        # Online = received a position in the last 60 seconds
        is_online = _is_recent(now, latest_app_pos.timestamp)

        active_sessions.append({
            "pilot_id": ts.pilot_id,
            "user_id": session_user_id,
            "pilot_name": pilot_name,
            "profile_type": session_profile_type,
            "task_id": ts.task_id,
            "task_name": task_name or ("Free Flight" if ts.task_id is None else None),
            "device_id": None,
            "source": PHONE_APP_POSITION_SOURCE,
            "battery_level": latest_app_pos.battery_level,
            "position_count": phone_position_count,
            "positions_last_60s": positions_last_60s,
            "started_at": ts.started_at.isoformat() if ts.started_at else None,
            "last_seen_at": latest_app_pos.timestamp.isoformat(),
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
        latest_pos_pilot_id = getattr(latest_pos, "pilot_id", None)
        resolved_owner_pilot_id = owner_pilot_id if owner_pilot_id is not None else latest_pos_pilot_id
        node_status = next((status_by_device[lookup_id] for lookup_id in lookup_ids if lookup_id in status_by_device), None)
        status_ts = node_status.last_seen_at if node_status is not None else None
        latest_pos_ts = getattr(latest_pos, "timestamp", None)
        latest_position_is_newer = False
        latest_ts = status_ts
        if latest_pos_ts is not None and _timestamp_value(latest_pos_ts) > _timestamp_value(latest_ts):
            latest_ts = latest_pos_ts
            latest_position_is_newer = True
        mesh_status = mesh_status_for_seen_at(now, latest_ts)
        source = (
            getattr(latest_pos, "source", None)
            if latest_position_is_newer and getattr(latest_pos, "source", None) is not None
            else node_status.last_source if node_status is not None and node_status.last_source is not None
            else getattr(latest_pos, "source", None) if latest_pos is not None else None
        )
        last_packet_type = (
            "POSITION_APP"
            if latest_position_is_newer and latest_pos is not None
            else node_status.last_packet_type if node_status is not None
            else "POSITION_APP" if latest_pos is not None
            else None
        )
        last_gateway_id = _status_gateway_id_for_latest(
            node_status,
            latest_position_is_newer=latest_position_is_newer,
            latest_position_ts=latest_pos_ts,
            source=source,
            packet_type=last_packet_type,
        )
        registered_mesh_devices.append({
            "owner_user_id": owner_user_id,
            "owner_name": owner_name,
            "owner_pilot_id": resolved_owner_pilot_id,
            "device_id": canonical_device_id,
            "label": device.label,
            "purpose": device.purpose,
            "is_connected": mesh_status == "live",
            "mesh_status": mesh_status,
            "last_seen_at": latest_ts.isoformat() if latest_ts else None,
            "last_packet_type": last_packet_type,
            "last_gateway_id": last_gateway_id,
            "last_gateway_display_name": (
                gateway_display_names.get(last_gateway_id)
                if last_gateway_id is not None
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
            "source": source,
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
