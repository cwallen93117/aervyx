from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Event, IGCUpload, PilotFlight, PilotFlightTrackPoint, Task, TrackPoint, User
from app.services.igc import ParsedIGC, TrackFix, parse_igc


@dataclass
class DerivedFlightStats:
    duration_seconds: int | None
    highest_altitude_m: float | None
    best_climb_mps: float | None
    launch_time: str | None
    landing_time: str | None
    launch_altitude_m: float | None
    landing_altitude_m: float | None
    fix_count: int
    total_track_distance_km: float
    max_ground_speed_kmh: float | None


def _altitude_m(point: TrackFix | TrackPoint | PilotFlightTrackPoint) -> float | None:
    gps_altitude = getattr(point, "gps_altitude_m", None)
    pressure_altitude = getattr(point, "pressure_altitude_m", None)
    if gps_altitude is not None:
        return float(gps_altitude)
    if pressure_altitude is not None:
        return float(pressure_altitude)
    return None


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def derive_flight_stats(points: Sequence[TrackFix | TrackPoint | PilotFlightTrackPoint]) -> DerivedFlightStats:
    if not points:
        return DerivedFlightStats(
            duration_seconds=None,
            highest_altitude_m=None,
            best_climb_mps=None,
            launch_time=None,
            landing_time=None,
            launch_altitude_m=None,
            landing_altitude_m=None,
            fix_count=0,
            total_track_distance_km=0.0,
            max_ground_speed_kmh=None,
        )

    ordered_points = sorted(points, key=lambda point: getattr(point, "recorded_at"))
    first_point = ordered_points[0]
    last_point = ordered_points[-1]
    duration_seconds = max(0, int((last_point.recorded_at - first_point.recorded_at).total_seconds()))
    altitudes = [_altitude_m(point) for point in ordered_points]
    valid_altitudes = [altitude for altitude in altitudes if altitude is not None]
    total_track_distance_m = 0.0
    max_ground_speed_kmh = 0.0
    best_climb_mps: float | None = None

    for index in range(1, len(ordered_points)):
        previous = ordered_points[index - 1]
        current = ordered_points[index]
        elapsed_seconds = (current.recorded_at - previous.recorded_at).total_seconds()
        if elapsed_seconds <= 0:
            continue
        segment_distance_m = _haversine_distance_m(previous.latitude, previous.longitude, current.latitude, current.longitude)
        total_track_distance_m += segment_distance_m
        max_ground_speed_kmh = max(max_ground_speed_kmh, (segment_distance_m / elapsed_seconds) * 3.6)
        previous_altitude = _altitude_m(previous)
        current_altitude = _altitude_m(current)
        if previous_altitude is not None and current_altitude is not None:
            climb_rate = (current_altitude - previous_altitude) / elapsed_seconds
            if best_climb_mps is None or climb_rate > best_climb_mps:
                best_climb_mps = climb_rate

    return DerivedFlightStats(
        duration_seconds=duration_seconds,
        highest_altitude_m=max(valid_altitudes) if valid_altitudes else None,
        best_climb_mps=best_climb_mps,
        launch_time=first_point.recorded_at.isoformat() if first_point.recorded_at else None,
        landing_time=last_point.recorded_at.isoformat() if last_point.recorded_at else None,
        launch_altitude_m=_altitude_m(first_point),
        landing_altitude_m=_altitude_m(last_point),
        fix_count=len(ordered_points),
        total_track_distance_km=round(total_track_distance_m / 1000, 3),
        max_ground_speed_kmh=round(max_ground_speed_kmh, 2) if max_ground_speed_kmh else None,
    )


def _logbook_site_name(session: Session, event_id: int | None) -> str:
    if not event_id:
        return ""
    event = session.get(Event, event_id)
    if event is None:
        return ""
    return (event.location or event.name or "").strip()


def sync_task_upload_to_logbook(
    session: Session,
    *,
    upload: IGCUpload,
    parsed: ParsedIGC,
) -> PilotFlight:
    stats = derive_flight_stats(parsed.fixes)
    metadata = dict(parsed.metadata)
    metadata["stats"] = {
        "launch_time": stats.launch_time,
        "landing_time": stats.landing_time,
        "launch_altitude_m": stats.launch_altitude_m,
        "landing_altitude_m": stats.landing_altitude_m,
        "fix_count": stats.fix_count,
        "total_track_distance_km": stats.total_track_distance_km,
        "max_ground_speed_kmh": stats.max_ground_speed_kmh,
    }
    flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == upload.id))
    if flight is None:
        flight = PilotFlight(
            pilot_id=upload.pilot_id,
            source_kind="task_upload",
            event_id=upload.event_id,
            task_id=upload.task_id,
            igc_upload_id=upload.id,
            flight_date=date.fromisoformat(str(parsed.metadata.get("flight_date"))) if parsed.metadata.get("flight_date") else upload.uploaded_at.date(),
        )
    flight.pilot_id = upload.pilot_id
    flight.source_kind = "task_upload"
    flight.event_id = upload.event_id
    flight.task_id = upload.task_id
    flight.igc_upload_id = upload.id
    flight.flight_date = date.fromisoformat(str(parsed.metadata.get("flight_date"))) if parsed.metadata.get("flight_date") else upload.uploaded_at.date()
    flight.site_name = _logbook_site_name(session, upload.event_id)
    flight.duration_seconds = stats.duration_seconds
    flight.highest_altitude_m = stats.highest_altitude_m
    flight.best_climb_mps = stats.best_climb_mps
    flight.filename = upload.filename
    flight.sha256 = upload.sha256
    flight.stored_path = upload.stored_path
    flight.metadata_json = metadata
    session.add(flight)
    session.flush()
    return flight


async def create_app_upload_flight(
    session: Session,
    *,
    user: User,
    filename: str,
    content: bytes,
    site_name: str | None = None,
    notes: str | None = None,
    flight_date_override: date | None = None,
) -> PilotFlight:
    if user.pilot_id is None:
        raise ValueError("This account is not linked to a pilot profile.")
    parsed = parse_igc(content)
    sha256 = hashlib.sha256(content).hexdigest()
    safe_filename = filename or "flight.igc"
    settings = get_settings()
    flight_dir = Path(settings.upload_root) / "logbook" / str(user.pilot_id) / sha256
    await asyncio.to_thread(flight_dir.mkdir, parents=True, exist_ok=True)
    stored_path = flight_dir / safe_filename
    if not await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.write_bytes, content)
    stats = derive_flight_stats(parsed.fixes)
    metadata = dict(parsed.metadata)
    metadata["stats"] = {
        "launch_time": stats.launch_time,
        "landing_time": stats.landing_time,
        "launch_altitude_m": stats.launch_altitude_m,
        "landing_altitude_m": stats.landing_altitude_m,
        "fix_count": stats.fix_count,
        "total_track_distance_km": stats.total_track_distance_km,
        "max_ground_speed_kmh": stats.max_ground_speed_kmh,
    }
    flight = PilotFlight(
        pilot_id=user.pilot_id,
        source_kind="app_upload",
        event_id=None,
        task_id=None,
        igc_upload_id=None,
        flight_date=flight_date_override or (date.fromisoformat(str(parsed.metadata.get("flight_date"))) if parsed.metadata.get("flight_date") else date.today()),
        site_name=(site_name or "").strip(),
        notes=notes.strip() if notes and notes.strip() else None,
        duration_seconds=stats.duration_seconds,
        highest_altitude_m=stats.highest_altitude_m,
        best_climb_mps=stats.best_climb_mps,
        filename=safe_filename,
        sha256=sha256,
        stored_path=str(stored_path),
        metadata_json=metadata,
    )
    session.add(flight)
    session.flush()
    for sequence, fix in enumerate(parsed.fixes, start=1):
        session.add(
            PilotFlightTrackPoint(
                flight_id=flight.id,
                sequence=sequence,
                recorded_at=fix.recorded_at,
                latitude=fix.latitude,
                longitude=fix.longitude,
                pressure_altitude_m=fix.pressure_altitude_m,
                gps_altitude_m=fix.gps_altitude_m,
            )
        )
    session.flush()
    return flight


def get_flight_track_points(session: Session, flight: PilotFlight) -> list[TrackPoint | PilotFlightTrackPoint]:
    if flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        if upload is None:
            return []
        return session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload.id).order_by(TrackPoint.sequence.asc())).all()
    return session.scalars(select(PilotFlightTrackPoint).where(PilotFlightTrackPoint.flight_id == flight.id).order_by(PilotFlightTrackPoint.sequence.asc())).all()


def delete_logbook_owned_track_points(session: Session, flight_ids: Iterable[int]) -> None:
    flight_ids = list(flight_ids)
    if not flight_ids:
        return
    session.execute(delete(PilotFlightTrackPoint).where(PilotFlightTrackPoint.flight_id.in_(flight_ids)))
