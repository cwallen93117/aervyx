from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select

from app.db import SessionLocal
from app.models import LivePosition, MeshDevice, MeshNodeStatus, Pilot, TrackingSession, User
from app.services.mesh_ids import mesh_device_id_lookup_variants, normalize_mesh_device_id
from app.services.tracking import subject_key_for_position


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _user_row(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "profile_type": user.profile_type,
        "pilot_id": user.pilot_id,
        "mesh_device_id": user.mesh_device_id,
        "is_active": user.is_active,
    }


def _pilot_row(pilot: Pilot) -> dict[str, Any]:
    return {
        "id": pilot.id,
        "first_name": pilot.first_name,
        "last_name": pilot.last_name,
        "email": pilot.email,
        "competition_number": pilot.competition_number,
        "civl_id": pilot.civl_id,
    }


def _device_row(device: MeshDevice) -> dict[str, Any]:
    return {
        "id": device.id,
        "owner_user_id": device.owner_user_id,
        "device_id": device.device_id,
        "label": device.label,
        "purpose": device.purpose,
        "is_active": device.is_active,
    }


def _position_row(position: LivePosition) -> dict[str, Any]:
    return {
        "id": str(position.id),
        "subject_key": subject_key_for_position(position),
        "pilot_id": position.pilot_id,
        "user_id": position.user_id,
        "task_id": position.task_id,
        "device_id": position.device_id,
        "source": position.source,
        "timestamp": _iso(position.timestamp),
        "created_at": _iso(position.created_at),
        "lat": position.lat,
        "lon": position.lon,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit tracker identity rows for a pilot/user/device.")
    parser.add_argument("--name", help="Case-insensitive user or pilot name fragment, e.g. 'messina'")
    parser.add_argument("--device-id", help="Meshtastic device id in canonical or bare form")
    parser.add_argument("--days", type=int, default=3, help="Live-position lookback window")
    args = parser.parse_args()

    normalized_device = normalize_mesh_device_id(args.device_id)
    device_variants = mesh_device_id_lookup_variants(normalized_device)
    name_like = f"%{args.name.lower()}%" if args.name else None
    since = datetime.now(UTC) - timedelta(days=args.days)

    with SessionLocal() as session:
        users_query = select(User)
        pilots_query = select(Pilot)
        if name_like:
            users_query = users_query.where(func.lower(User.full_name).like(name_like))
            pilots_query = pilots_query.where(
                or_(
                    func.lower(Pilot.first_name).like(name_like),
                    func.lower(Pilot.last_name).like(name_like),
                    func.lower((Pilot.first_name + " " + Pilot.last_name)).like(name_like),
                )
            )
        else:
            users_query = users_query.where(False)
            pilots_query = pilots_query.where(False)

        users = session.scalars(users_query.order_by(User.id.asc())).all()
        pilots = session.scalars(pilots_query.order_by(Pilot.id.asc())).all()
        pilot_ids = {pilot.id for pilot in pilots} | {user.pilot_id for user in users if user.pilot_id is not None}
        user_ids = {user.id for user in users}

        devices_query = select(MeshDevice)
        device_filters = []
        if user_ids:
            device_filters.append(MeshDevice.owner_user_id.in_(user_ids))
        if device_variants:
            device_filters.append(MeshDevice.device_id.in_(device_variants))
        devices = (
            session.scalars(devices_query.where(or_(*device_filters)).order_by(MeshDevice.device_id.asc())).all()
            if device_filters
            else []
        )
        all_device_ids = {device.device_id for device in devices} | set(device_variants)

        position_filters = [LivePosition.timestamp >= since]
        subject_filters = []
        if pilot_ids:
            subject_filters.append(LivePosition.pilot_id.in_(pilot_ids))
        if user_ids:
            subject_filters.append(LivePosition.user_id.in_(user_ids))
        if all_device_ids:
            subject_filters.append(LivePosition.device_id.in_(all_device_ids))
        positions = (
            session.scalars(
                select(LivePosition)
                .where(*position_filters, or_(*subject_filters))
                .order_by(LivePosition.timestamp.desc())
                .limit(100)
            ).all()
            if subject_filters
            else []
        )

        sessions = (
            session.scalars(
                select(TrackingSession)
                .where(
                    or_(
                        TrackingSession.pilot_id.in_(pilot_ids) if pilot_ids else False,
                        TrackingSession.user_id.in_(user_ids) if user_ids else False,
                    )
                )
                .order_by(TrackingSession.last_seen_at.desc())
                .limit(50)
            ).all()
            if pilot_ids or user_ids
            else []
        )
        statuses = (
            session.scalars(select(MeshNodeStatus).where(MeshNodeStatus.device_id.in_(all_device_ids))).all()
            if all_device_ids
            else []
        )

    print(json.dumps({
        "query": {"name": args.name, "device_id": normalized_device, "days": args.days},
        "users": [_user_row(user) for user in users],
        "pilots": [_pilot_row(pilot) for pilot in pilots],
        "mesh_devices": [_device_row(device) for device in devices],
        "live_positions": [_position_row(position) for position in positions],
        "tracking_sessions": [
            {
                "id": str(row.id),
                "pilot_id": row.pilot_id,
                "user_id": row.user_id,
                "task_id": row.task_id,
                "is_active": row.is_active,
                "position_count": row.position_count,
                "started_at": _iso(row.started_at),
                "last_seen_at": _iso(row.last_seen_at),
            }
            for row in sessions
        ],
        "mesh_node_statuses": [
            {
                "device_id": row.device_id,
                "last_seen_at": _iso(row.last_seen_at),
                "last_source": row.last_source,
                "last_gateway_id": row.last_gateway_id,
                "last_topic": row.last_topic,
                "packet_count": row.packet_count,
            }
            for row in statuses
        ],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
