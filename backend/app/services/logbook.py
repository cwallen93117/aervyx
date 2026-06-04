from __future__ import annotations

import asyncio
import hashlib
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time as dt_time
from pathlib import Path
from typing import Callable, Iterable, Literal, Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Event, EventPilot, FlightSite, IGCUpload, Pilot, PilotFlight, PilotFlightTrackPoint, SiteSettings, Task, TrackPoint, User
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
    time_in_thermals_seconds: int
    time_on_glide_seconds: int
    total_track_distance_km: float
    max_ground_speed_kmh: float | None


@dataclass
class LogbookFolderImportItem:
    file_key: str
    sha256: str
    filename: str
    relative_path: str | None
    detected_pilot_name: str | None
    reason: str
    flight_id: int | None = None


@dataclass
class LogbookFolderImportResult:
    imported: list[LogbookFolderImportItem]
    skipped: list[LogbookFolderImportItem]
    review_needed: list[LogbookFolderImportItem]


@dataclass
class FlightSiteRescanStats:
    scanned_count: int
    matched_count: int
    unmatched_count: int


def _altitude_m(point: TrackFix | TrackPoint | PilotFlightTrackPoint) -> float | None:
    gps_altitude = getattr(point, "gps_altitude_m", None)
    pressure_altitude = getattr(point, "pressure_altitude_m", None)
    if gps_altitude is not None:
        return float(gps_altitude)
    if pressure_altitude is not None:
        return float(pressure_altitude)
    return None


def _pressure_altitude_m(point: TrackFix | TrackPoint | PilotFlightTrackPoint) -> float | None:
    pressure_altitude = getattr(point, "pressure_altitude_m", None)
    if pressure_altitude is None:
        return None
    return float(pressure_altitude)


def _gps_altitude_m(point: TrackFix | TrackPoint | PilotFlightTrackPoint) -> float | None:
    gps_altitude = getattr(point, "gps_altitude_m", None)
    if gps_altitude is None:
        return None
    return float(gps_altitude)


def _stats_altitude_selector(
    points: Sequence[TrackFix | TrackPoint | PilotFlightTrackPoint],
) -> Callable[[TrackFix | TrackPoint | PilotFlightTrackPoint], float | None]:
    if any(_pressure_altitude_m(point) is not None for point in points):
        return _pressure_altitude_m
    return _gps_altitude_m


def _validated_climb_rate(
    previous_altitude: float | None,
    current_altitude: float | None,
    elapsed_seconds: float,
    *,
    max_abs_climb_mps: float = 10.0,
) -> float | None:
    if previous_altitude is None or current_altitude is None or elapsed_seconds <= 0:
        return None
    climb_rate = (current_altitude - previous_altitude) / elapsed_seconds
    if not math.isfinite(climb_rate):
        return None
    if abs(climb_rate) > max_abs_climb_mps:
        return None
    return climb_rate


def _haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_m = 6371000
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    return radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _site_match_radius_m(session: Session) -> int:
    settings = session.get(SiteSettings, 1)
    radius = getattr(settings, "site_match_radius_m", None) if settings is not None else None
    if radius is None or radius <= 0:
        return 1000
    return int(radius)


def _first_point_coordinates(points: Sequence[TrackFix | TrackPoint | PilotFlightTrackPoint]) -> tuple[float, float] | None:
    if not points:
        return None
    first_point = sorted(points, key=lambda point: getattr(point, "recorded_at"))[0]
    return float(first_point.latitude), float(first_point.longitude)


def find_matching_site(session: Session, latitude: float, longitude: float) -> FlightSite | None:
    sites = session.scalars(select(FlightSite).where(FlightSite.is_active.is_(True)).order_by(FlightSite.name.asc())).all()
    if not sites:
        return None
    match_radius_m = _site_match_radius_m(session)
    best_match: FlightSite | None = None
    best_distance_m: float | None = None
    for site in sites:
        distance_m = _haversine_distance_m(latitude, longitude, site.latitude, site.longitude)
        if distance_m > match_radius_m:
            continue
        if best_distance_m is None or distance_m < best_distance_m:
            best_match = site
            best_distance_m = distance_m
    return best_match


def _matching_site_for_points(
    session: Session,
    points: Sequence[TrackFix | TrackPoint | PilotFlightTrackPoint],
) -> FlightSite | None:
    coordinates = _first_point_coordinates(points)
    if coordinates is None:
        return None
    return find_matching_site(session, coordinates[0], coordinates[1])


def assign_site_to_flight(
    session: Session,
    *,
    flight: PilotFlight,
    points: Sequence[TrackFix | TrackPoint | PilotFlightTrackPoint],
    fallback_site_name: str | None = None,
) -> bool:
    matched_site = _matching_site_for_points(session, points)
    if matched_site is not None:
        flight.site_id = matched_site.id
        flight.site_name = matched_site.name
        # Increment the site's flight counter
        matched_site.flight_count = (matched_site.flight_count or 0) + 1
        session.add(matched_site)
        return True
    if not flight.site_name and fallback_site_name:
        flight.site_name = fallback_site_name.strip()
    return False


def _recompute_site_flight_counts(session: Session) -> None:
    sites = session.scalars(select(FlightSite).order_by(FlightSite.id.asc())).all()
    if not sites:
        return

    session.flush()
    counts_by_site_id = dict(
        session.execute(
            select(PilotFlight.site_id, func.count(PilotFlight.id))
            .where(PilotFlight.site_id.is_not(None))
            .group_by(PilotFlight.site_id)
        ).all()
    )

    for site in sites:
        site.flight_count = int(counts_by_site_id.get(site.id, 0))
        session.add(site)


def _normalize_identity_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _identity_tokens(value: str | None) -> set[str]:
    normalized = _normalize_identity_text(value)
    return {token for token in normalized.split() if token}


def _evaluate_pilot_match(user: User, pilot: Pilot | None, detected_pilot_name: str | None) -> tuple[Literal["auto", "review", "skip"], str]:
    detected_normalized = _normalize_identity_text(detected_pilot_name)
    if not detected_normalized:
        return ("review", "This file does not include a pilot name in the IGC header.")

    candidate_names = {
        _normalize_identity_text(user.full_name),
        _normalize_identity_text(f"{pilot.first_name} {pilot.last_name}" if pilot else None),
        _normalize_identity_text(f"{pilot.last_name} {pilot.first_name}" if pilot else None),
    }
    candidate_names.discard("")
    if detected_normalized in candidate_names:
        return ("auto", "Pilot name matches the signed-in pilot.")

    detected_tokens = _identity_tokens(detected_pilot_name)
    if not detected_tokens:
        return ("review", "The IGC pilot name could not be normalized confidently.")

    full_name_tokens = _identity_tokens(user.full_name)
    if full_name_tokens and full_name_tokens.issubset(detected_tokens):
        return ("auto", "Pilot name tokens match the signed-in pilot.")

    first_name = _normalize_identity_text(pilot.first_name if pilot else None)
    last_name = _normalize_identity_text(pilot.last_name if pilot else None)
    first_tokens = _identity_tokens(first_name)
    last_tokens = _identity_tokens(last_name)
    if first_tokens and last_tokens and first_tokens.issubset(detected_tokens) and last_tokens.issubset(detected_tokens):
        return ("auto", "Pilot first and last name match the IGC header.")

    first_token = next(iter(first_tokens), "")
    last_token = next(iter(last_tokens), "")
    if last_token and last_token in detected_tokens:
        if first_token and any(token.startswith(first_token[:1]) for token in detected_tokens):
            return ("review", "Last name matches, but the first name is only a partial match.")
        return ("review", "The IGC last name matches, but the full pilot name is not exact.")

    if first_token and first_token in detected_tokens:
        return ("review", "The IGC first name matches, but the full pilot name is not exact.")

    return ("skip", "This IGC pilot name does not match the signed-in pilot.")


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
            time_in_thermals_seconds=0,
            time_on_glide_seconds=0,
            total_track_distance_km=0.0,
            max_ground_speed_kmh=None,
        )

    ordered_points = sorted(points, key=lambda point: getattr(point, "recorded_at"))
    stats_altitude = _stats_altitude_selector(ordered_points)
    first_point = ordered_points[0]
    last_point = ordered_points[-1]
    duration_seconds = max(0, int((last_point.recorded_at - first_point.recorded_at).total_seconds()))
    altitudes = [stats_altitude(point) for point in ordered_points]
    valid_altitudes = [altitude for altitude in altitudes if altitude is not None]
    total_track_distance_m = 0.0
    max_ground_speed_kmh = 0.0
    best_climb_mps: float | None = None
    segment_climb_rates: list[float] = []
    segment_durations: list[float] = []

    for index in range(1, len(ordered_points)):
        previous = ordered_points[index - 1]
        current = ordered_points[index]
        elapsed_seconds = (current.recorded_at - previous.recorded_at).total_seconds()
        if elapsed_seconds <= 0:
            continue
        segment_distance_m = _haversine_distance_m(previous.latitude, previous.longitude, current.latitude, current.longitude)
        total_track_distance_m += segment_distance_m
        max_ground_speed_kmh = max(max_ground_speed_kmh, (segment_distance_m / elapsed_seconds) * 3.6)
        previous_altitude = stats_altitude(previous)
        current_altitude = stats_altitude(current)
        climb_rate = _validated_climb_rate(previous_altitude, current_altitude, elapsed_seconds)
        if climb_rate is not None:
            if best_climb_mps is None or climb_rate > best_climb_mps:
                best_climb_mps = climb_rate
            segment_climb_rates.append(climb_rate)
            segment_durations.append(elapsed_seconds)

    time_in_thermals_seconds = 0.0
    time_on_glide_seconds = 0.0
    for index, climb_rate in enumerate(segment_climb_rates):
        window_start = max(0, index - 1)
        window_end = min(len(segment_climb_rates), index + 2)
        smoothed_climb_rate = sum(segment_climb_rates[window_start:window_end]) / (window_end - window_start)
        if smoothed_climb_rate >= 0.5:
            time_in_thermals_seconds += segment_durations[index]
        else:
            time_on_glide_seconds += segment_durations[index]

    return DerivedFlightStats(
        duration_seconds=duration_seconds,
        highest_altitude_m=max(valid_altitudes) if valid_altitudes else None,
        best_climb_mps=best_climb_mps,
        launch_time=first_point.recorded_at.isoformat() if first_point.recorded_at else None,
        landing_time=last_point.recorded_at.isoformat() if last_point.recorded_at else None,
        launch_altitude_m=stats_altitude(first_point),
        landing_altitude_m=stats_altitude(last_point),
        time_in_thermals_seconds=int(round(time_in_thermals_seconds)),
        time_on_glide_seconds=int(round(time_on_glide_seconds)),
        total_track_distance_km=round(total_track_distance_m / 1000, 3),
        max_ground_speed_kmh=round(max_ground_speed_kmh, 2) if max_ground_speed_kmh else None,
    )


def _apply_derived_stats_to_flight(
    flight: PilotFlight,
    *,
    stats: DerivedFlightStats,
    metadata: dict | None = None,
) -> None:
    flight.duration_seconds = stats.duration_seconds
    flight.highest_altitude_m = stats.highest_altitude_m
    flight.best_climb_mps = stats.best_climb_mps
    if metadata is not None:
        metadata["stats"] = _stats_metadata(stats)
        flight.metadata_json = metadata


def recompute_track_backed_flight_stats(session: Session, flight: PilotFlight) -> bool:
    points = get_flight_track_points(session, flight)
    if not points:
        return False
    stats = derive_flight_stats(points)
    metadata = dict(flight.metadata_json) if isinstance(flight.metadata_json, dict) else {}
    _apply_derived_stats_to_flight(flight, stats=stats, metadata=metadata)
    session.add(flight)
    return True


def _logbook_site_name(session: Session, event_id: int | None) -> str:
    if not event_id:
        return ""
    event = session.get(Event, event_id)
    if event is None:
        return ""
    return (event.location or event.name or "").strip()


def _stats_metadata(stats: DerivedFlightStats) -> dict[str, str | float | int | None]:
    return {
        "launch_time": stats.launch_time,
        "landing_time": stats.landing_time,
        "launch_altitude_m": stats.launch_altitude_m,
        "landing_altitude_m": stats.landing_altitude_m,
        "time_in_thermals_seconds": stats.time_in_thermals_seconds,
        "time_on_glide_seconds": stats.time_on_glide_seconds,
        "total_track_distance_km": stats.total_track_distance_km,
        "max_ground_speed_kmh": stats.max_ground_speed_kmh,
    }


async def _create_logbook_owned_flight_from_parsed(
    session: Session,
    *,
    pilot_id: int,
    source_kind: str,
    parsed: ParsedIGC,
    sha256: str,
    filename: str,
    content: bytes,
    site_name: str | None = None,
    notes: str | None = None,
    flight_date_override: date | None = None,
    task_link_metadata: dict | None = None,
) -> PilotFlight:
    safe_filename = filename or "flight.igc"
    settings = get_settings()
    flight_dir = Path(settings.upload_root) / "logbook" / str(pilot_id) / sha256
    await asyncio.to_thread(flight_dir.mkdir, parents=True, exist_ok=True)
    stored_path = flight_dir / safe_filename
    if not await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.write_bytes, content)
    stats = derive_flight_stats(parsed.fixes)
    metadata = dict(parsed.metadata)
    if task_link_metadata:
        metadata.update(task_link_metadata)
    flight = PilotFlight(
        pilot_id=pilot_id,
        source_kind=source_kind,
        event_id=None,
        task_id=None,
        site_id=None,
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
    _apply_derived_stats_to_flight(flight, stats=stats, metadata=metadata)
    session.add(flight)
    assign_site_to_flight(session, flight=flight, points=parsed.fixes, fallback_site_name=site_name)
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


def _parsed_flight_date(parsed: ParsedIGC, flight_date_override: date | None = None) -> date:
    if flight_date_override is not None:
        return flight_date_override
    if parsed.metadata.get("flight_date"):
        return date.fromisoformat(str(parsed.metadata["flight_date"]))
    return date.today()


def _same_day_task_candidates(session: Session, *, pilot_id: int, flight_date: date) -> list[Task]:
    return session.scalars(
        select(Task)
        .join(EventPilot, EventPilot.event_id == Task.event_id)
        .where(
            EventPilot.pilot_id == pilot_id,
            Task.task_date == flight_date,
        )
        .order_by(Task.id.asc())
    ).all()


def _auto_link_task_candidate(
    session: Session,
    *,
    user: User,
    flight_date: date,
    task_candidates: Sequence[Task],
) -> Task | None:
    active_candidates = [task for task in task_candidates if task.status == "active"]
    if len(active_candidates) == 1:
        return active_candidates[0]
    if len(task_candidates) == 1:
        return task_candidates[0]

    from app.services.tracking import resolve_active_task_id_for_user

    resolver_now = datetime.combine(flight_date, dt_time(12, 0), tzinfo=UTC)
    resolved_task_id = resolve_active_task_id_for_user(session, user, now=resolver_now)
    if resolved_task_id is None:
        return None
    resolved = next((task for task in task_candidates if task.id == resolved_task_id), None)
    if resolved is None:
        return None
    if resolved.status in {"active", "draft"} and resolved.task_date == flight_date:
        return resolved
    return None


def sync_task_upload_to_logbook(
    session: Session,
    *,
    upload: IGCUpload,
    parsed: ParsedIGC,
) -> PilotFlight:
    stats = derive_flight_stats(parsed.fixes)
    metadata = dict(parsed.metadata)
    flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == upload.id))
    if flight is None:
        flight = PilotFlight(
            pilot_id=upload.pilot_id,
            source_kind="task_upload",
            event_id=upload.event_id,
            task_id=upload.task_id,
            site_id=None,
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
    flight.filename = upload.filename
    flight.sha256 = upload.sha256
    flight.stored_path = upload.stored_path
    _apply_derived_stats_to_flight(flight, stats=stats, metadata=metadata)
    assign_site_to_flight(session, flight=flight, points=parsed.fixes, fallback_site_name=_logbook_site_name(session, upload.event_id))
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
    flight_date = _parsed_flight_date(parsed, flight_date_override)
    task_candidates = _same_day_task_candidates(session, pilot_id=user.pilot_id, flight_date=flight_date)
    task_candidate = _auto_link_task_candidate(session, user=user, flight_date=flight_date, task_candidates=task_candidates)
    if task_candidate is not None:
        from app.services.task_uploads import store_task_upload

        stored = await store_task_upload(
            session,
            task_candidate,
            filename=filename,
            content=content,
            pilot_id=user.pilot_id,
            uploaded_by_user_id=user.id,
            upload_source="app",
            parsed=parsed,
        )
        flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == stored.upload.id))
        if flight is not None:
            return flight

    task_link_metadata = None
    if len(task_candidates) > 1:
        task_link_metadata = {
            "task_link_status": "ambiguous",
            "task_link_candidate_ids": [task.id for task in task_candidates],
        }
    return await _create_logbook_owned_flight_from_parsed(
        session,
        pilot_id=user.pilot_id,
        source_kind="app_upload",
        parsed=parsed,
        sha256=sha256,
        filename=filename,
        content=content,
        site_name=site_name,
        notes=notes,
        flight_date_override=flight_date_override,
        task_link_metadata=task_link_metadata,
    )


async def import_logbook_folder_files(
    session: Session,
    *,
    user: User,
    files: list[tuple[str, str | None, bytes]],
    confirmed_file_keys: set[str] | None = None,
) -> LogbookFolderImportResult:
    if user.pilot_id is None:
        raise ValueError("This account is not linked to a pilot profile.")
    pilot = session.get(Pilot, user.pilot_id)
    existing_hashes = {
        sha
        for sha in session.scalars(select(PilotFlight.sha256).where(PilotFlight.pilot_id == user.pilot_id, PilotFlight.sha256.is_not(None))).all()
        if sha
    }
    confirmed_file_keys = confirmed_file_keys or set()
    batch_hashes: set[str] = set()
    result = LogbookFolderImportResult(imported=[], skipped=[], review_needed=[])

    for file_key, relative_path, content in files:
        filename = Path(relative_path or file_key).name
        try:
            parsed = parse_igc(content)
        except ValueError as exc:
            result.skipped.append(
                LogbookFolderImportItem(
                    file_key=file_key,
                    sha256="",
                    filename=filename,
                    relative_path=relative_path,
                    detected_pilot_name=None,
                    reason=str(exc),
                )
            )
            continue

        sha256 = hashlib.sha256(content).hexdigest()
        detected_pilot_name = str(parsed.metadata.get("pilot_name") or "").strip() or None
        if sha256 in existing_hashes or sha256 in batch_hashes:
            result.skipped.append(
                LogbookFolderImportItem(
                    file_key=file_key,
                    sha256=sha256,
                    filename=filename,
                    relative_path=relative_path,
                    detected_pilot_name=detected_pilot_name,
                    reason="This IGC is already in the logbook.",
                )
            )
            continue

        match_status, reason = _evaluate_pilot_match(user, pilot, detected_pilot_name)
        if match_status == "skip":
            result.skipped.append(
                LogbookFolderImportItem(
                    file_key=file_key,
                    sha256=sha256,
                    filename=filename,
                    relative_path=relative_path,
                    detected_pilot_name=detected_pilot_name,
                    reason=reason,
                )
            )
            continue

        if match_status == "review" and file_key not in confirmed_file_keys:
            result.review_needed.append(
                LogbookFolderImportItem(
                    file_key=file_key,
                    sha256=sha256,
                    filename=filename,
                    relative_path=relative_path,
                    detected_pilot_name=detected_pilot_name,
                    reason=reason,
                )
            )
            continue

        flight_date = _parsed_flight_date(parsed)
        task_candidates = _same_day_task_candidates(session, pilot_id=user.pilot_id, flight_date=flight_date)
        task_candidate = _auto_link_task_candidate(session, user=user, flight_date=flight_date, task_candidates=task_candidates)
        if task_candidate is not None:
            from app.services.task_uploads import store_task_upload

            stored = await store_task_upload(
                session,
                task_candidate,
                filename=filename,
                content=content,
                pilot_id=user.pilot_id,
                uploaded_by_user_id=user.id,
                upload_source="app",
                parsed=parsed,
            )
            flight = session.scalar(select(PilotFlight).where(PilotFlight.igc_upload_id == stored.upload.id))
            if flight is None:
                flight = await _create_logbook_owned_flight_from_parsed(
                    session,
                    pilot_id=user.pilot_id,
                    source_kind="app_upload",
                    parsed=parsed,
                    sha256=sha256,
                    filename=filename,
                    content=content,
                )
            import_reason = "Imported into the task scores and pilot logbook."
        else:
            task_link_metadata = None
            if len(task_candidates) > 1:
                task_link_metadata = {
                    "task_link_status": "ambiguous",
                    "task_link_candidate_ids": [task.id for task in task_candidates],
                }
            flight = await _create_logbook_owned_flight_from_parsed(
                session,
                pilot_id=user.pilot_id,
                source_kind="app_upload",
                parsed=parsed,
                sha256=sha256,
                filename=filename,
                content=content,
                task_link_metadata=task_link_metadata,
            )
            import_reason = "Imported into the pilot logbook."
        batch_hashes.add(sha256)
        existing_hashes.add(sha256)
        result.imported.append(
            LogbookFolderImportItem(
                file_key=file_key,
                sha256=sha256,
                filename=filename,
                relative_path=relative_path,
                detected_pilot_name=detected_pilot_name,
                reason=import_reason,
                flight_id=flight.id,
            )
        )

    return result


async def attach_igc_to_existing_flight(
    session: Session,
    *,
    flight: PilotFlight,
    filename: str,
    content: bytes,
) -> PilotFlight:
    parsed = parse_igc(content)
    sha256 = hashlib.sha256(content).hexdigest()
    safe_filename = filename or "flight.igc"
    settings = get_settings()
    flight_dir = Path(settings.upload_root) / "logbook" / str(flight.pilot_id) / sha256
    await asyncio.to_thread(flight_dir.mkdir, parents=True, exist_ok=True)
    stored_path = flight_dir / safe_filename
    if not await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.write_bytes, content)

    previous_path = flight.stored_path
    stats = derive_flight_stats(parsed.fixes)
    metadata = dict(parsed.metadata)
    session.execute(delete(PilotFlightTrackPoint).where(PilotFlightTrackPoint.flight_id == flight.id))
    flight.source_kind = "app_upload"
    flight.filename = safe_filename
    flight.sha256 = sha256
    flight.stored_path = str(stored_path)
    _apply_derived_stats_to_flight(flight, stats=stats, metadata=metadata)
    assign_site_to_flight(session, flight=flight, points=parsed.fixes, fallback_site_name=flight.site_name)
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

    if previous_path and previous_path != str(stored_path):
        previous_file = Path(previous_path)
        if previous_file.exists():
            previous_file.unlink()
            try:
                previous_file.parent.rmdir()
            except OSError:
                pass
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


@dataclass
class ScanIgcResult:
    new_sites_created: int
    flights_matched: int
    total_igc_scanned: int
    sites: list[FlightSite]


def _reverse_geocode(lat: float, lon: float) -> tuple[str, str]:
    """Look up nearest city and state from GPS coordinates using Nominatim.

    Returns (city, state) or ("Unknown", "Unknown") on failure.
    """
    import urllib.request
    import json

    url = (
        f"https://nominatim.openstreetmap.org/reverse"
        f"?lat={lat}&lon={lon}&format=json&zoom=10&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Aervyx-Scoring/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        addr = data.get("address", {})
        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("village")
            or addr.get("hamlet")
            or addr.get("county")
            or "Unknown"
        )
        state = addr.get("state", "Unknown")
        return city, state
    except Exception:
        return "Unknown", "Unknown"


def scan_igc_for_new_sites(session: Session) -> ScanIgcResult:
    """Scan all IGC files (from PilotFlight and IGCUpload) for unique takeoff
    locations. For each cluster of takeoffs not matching an existing site,
    create a new FlightSite with name='Unknown', look up city/state via
    reverse geocoding, and set flight_count.
    """
    match_radius_m = _site_match_radius_m(session)

    # Gather all existing sites
    existing_sites: list[FlightSite] = list(
        session.scalars(select(FlightSite).order_by(FlightSite.id.asc())).all()
    )

    # Gather all flights that have track points
    flights: list[PilotFlight] = list(
        session.scalars(
            select(PilotFlight)
            .where(PilotFlight.source_kind.in_(("task_upload", "app_upload")))
            .order_by(PilotFlight.id.asc())
        ).all()
    )

    total_igc_scanned = 0

    # Collect all takeoff coordinates: (lat, lon, flight)
    takeoff_points: list[tuple[float, float, PilotFlight]] = []
    for flight in flights:
        points = get_flight_track_points(session, flight)
        if not points:
            continue
        total_igc_scanned += 1
        coords = _first_point_coordinates(points)
        if coords is not None:
            takeoff_points.append((coords[0], coords[1], flight))

    # Cluster takeoffs: for each takeoff, check if it matches an existing site
    # or a newly-discovered cluster. A cluster is represented by its centroid.
    @dataclass
    class TakeoffCluster:
        lat_sum: float
        lon_sum: float
        count: int
        flights: list[PilotFlight]

        @property
        def lat(self) -> float:
            return self.lat_sum / self.count

        @property
        def lon(self) -> float:
            return self.lon_sum / self.count

    new_clusters: list[TakeoffCluster] = []
    site_flight_counts: dict[int, int] = {}  # site_id -> additional flight count

    for lat, lon, flight in takeoff_points:
        # Check against existing sites
        matched_existing = False
        for site in existing_sites:
            if _haversine_distance_m(lat, lon, site.latitude, site.longitude) <= match_radius_m:
                site_flight_counts[site.id] = site_flight_counts.get(site.id, 0) + 1
                if flight.site_id is None:
                    flight.site_id = site.id
                    flight.site_name = site.name
                    session.add(flight)
                matched_existing = True
                break

        if matched_existing:
            continue

        # Check against new clusters
        matched_cluster = False
        for cluster in new_clusters:
            if _haversine_distance_m(lat, lon, cluster.lat, cluster.lon) <= match_radius_m:
                cluster.lat_sum += lat
                cluster.lon_sum += lon
                cluster.count += 1
                cluster.flights.append(flight)
                matched_cluster = True
                break

        if not matched_cluster:
            new_clusters.append(TakeoffCluster(
                lat_sum=lat,
                lon_sum=lon,
                count=1,
                flights=[flight],
            ))

    # Update flight_count for existing sites
    for site in existing_sites:
        count = site_flight_counts.get(site.id, 0)
        if count > 0:
            site.flight_count = count
            session.add(site)

    # Create new sites from clusters
    new_sites_created: list[FlightSite] = []
    for cluster in new_clusters:
        city, state = _reverse_geocode(cluster.lat, cluster.lon)
        city_state = f"{city}, {state}" if city != "Unknown" or state != "Unknown" else ""
        site = FlightSite(
            name="Unknown",
            city_state=city_state,
            latitude=round(cluster.lat, 6),
            longitude=round(cluster.lon, 6),
            is_active=True,
            flight_count=cluster.count,
        )
        session.add(site)
        session.flush()  # get the site.id

        # Assign flights to the new site
        for flight in cluster.flights:
            flight.site_id = site.id
            flight.site_name = site.name
            session.add(flight)

        new_sites_created.append(site)
        existing_sites.append(site)  # so subsequent clusters can match

    flights_matched = sum(site_flight_counts.values()) + sum(c.count for c in new_clusters)

    return ScanIgcResult(
        new_sites_created=len(new_sites_created),
        flights_matched=flights_matched,
        total_igc_scanned=total_igc_scanned,
        sites=new_sites_created,
    )


def rescan_unmatched_flights_for_sites(session: Session) -> FlightSiteRescanStats:
    flights = session.scalars(
        select(PilotFlight)
        .where(
            PilotFlight.source_kind.in_(("task_upload", "app_upload")),
        )
        .order_by(PilotFlight.flight_date.desc(), PilotFlight.id.desc())
    ).all()
    scanned_count = 0
    matched_count = 0
    for flight in flights:
        points = get_flight_track_points(session, flight)
        if not points:
            continue
        scanned_count += 1

        matched_site = _matching_site_for_points(session, points)
        if matched_site is not None:
            flight.site_id = matched_site.id
            flight.site_name = matched_site.name
            session.add(flight)
            matched_count += 1

    _recompute_site_flight_counts(session)

    unmatched_count = scanned_count - matched_count
    return FlightSiteRescanStats(
        scanned_count=scanned_count,
        matched_count=matched_count,
        unmatched_count=unmatched_count,
    )
