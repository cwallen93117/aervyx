from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user
from sqlalchemy import delete, select, update

from app.models import Event, FlightSite, IGCUpload, PilotFlight, PilotFlightTrackPoint, ScoreResult, Task, TaskPoint, TaskScoringInput, TrackPoint, User
from app.schemas import (
    LogbookBulkDeleteRequest,
    LogbookBulkDeleteResponse,
    LogbookFlightCreate,
    LogbookFlightDetailResponse,
    LogbookFlightStatsResponse,
    LogbookFlightSummaryResponse,
    LogbookFlightUpdate,
    LogbookFolderImportItemResponse,
    LogbookFolderImportResponse,
)
from app.services.logbook import attach_igc_to_existing_flight, create_app_upload_flight, derive_flight_stats, get_flight_track_points, import_logbook_folder_files
from app.services.replay_tracks import DEFAULT_REPLAY_MAX_POINTS, simplify_replay_points

router = APIRouter(prefix="/api/logbook", tags=["logbook"])


def _require_pilot_profile(user: User) -> int:
    if user.pilot_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This account is not linked to a pilot profile.")
    return user.pilot_id


def _flight_for_user(session: Session, user: User, flight_id: int) -> PilotFlight:
    pilot_id = _require_pilot_profile(user)
    flight = session.get(PilotFlight, flight_id)
    if flight is None or flight.pilot_id != pilot_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flight not found")
    return flight


def _trackbacked_download_path(session: Session, flight: PilotFlight) -> Path | None:
    if flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        if upload is not None:
            candidate = Path(upload.stored_path)
            if candidate.exists():
                return candidate
    if flight.stored_path:
        candidate = Path(flight.stored_path)
        if candidate.exists():
            return candidate
    return None


def _cleanup_stored_file(stored_path: str | None) -> None:
    if not stored_path:
        return
    candidate = Path(stored_path)
    if not candidate.exists():
        return
    candidate.unlink()
    try:
        candidate.parent.rmdir()
    except OSError:
        pass


def _delete_flight_records(session: Session, user: User, flight: PilotFlight) -> list[str | None]:
    cleanup_paths: list[str | None] = []
    if flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        cleanup_paths.append(upload.stored_path if upload is not None else None)
        session.execute(
            update(TaskScoringInput)
            .where(TaskScoringInput.selected_upload_id == flight.igc_upload_id)
            .values(selected_upload_id=None, status_override=None, updated_by_user_id=user.id)
        )
        session.execute(delete(ScoreResult).where(ScoreResult.upload_id == flight.igc_upload_id))
        session.execute(delete(TrackPoint).where(TrackPoint.upload_id == flight.igc_upload_id))
        session.execute(delete(PilotFlight).where(PilotFlight.igc_upload_id == flight.igc_upload_id))
        session.execute(delete(IGCUpload).where(IGCUpload.id == flight.igc_upload_id))
        return cleanup_paths

    cleanup_paths.append(flight.stored_path)
    session.execute(delete(PilotFlightTrackPoint).where(PilotFlightTrackPoint.flight_id == flight.id))
    session.execute(delete(PilotFlight).where(PilotFlight.id == flight.id))
    return cleanup_paths


def _build_stats_payload(flight: PilotFlight, points: list[TrackPoint | PilotFlightTrackPoint]) -> LogbookFlightStatsResponse:
    if points:
        stats = derive_flight_stats(points)
        return LogbookFlightStatsResponse(
            duration_seconds=stats.duration_seconds,
            highest_altitude_m=stats.highest_altitude_m,
            best_climb_mps=stats.best_climb_mps,
            launch_time=stats.launch_time,
            landing_time=stats.landing_time,
            launch_altitude_m=stats.launch_altitude_m,
            landing_altitude_m=stats.landing_altitude_m,
            time_in_thermals_seconds=stats.time_in_thermals_seconds,
            time_on_glide_seconds=stats.time_on_glide_seconds,
            total_track_distance_km=stats.total_track_distance_km,
            max_ground_speed_kmh=stats.max_ground_speed_kmh,
        )
    metadata_stats = flight.metadata_json.get("stats", {}) if isinstance(flight.metadata_json, dict) else {}
    return LogbookFlightStatsResponse(
        duration_seconds=flight.duration_seconds,
        highest_altitude_m=flight.highest_altitude_m,
        best_climb_mps=flight.best_climb_mps,
        launch_time=metadata_stats.get("launch_time"),
        landing_time=metadata_stats.get("landing_time"),
        launch_altitude_m=metadata_stats.get("launch_altitude_m"),
        landing_altitude_m=metadata_stats.get("landing_altitude_m"),
        time_in_thermals_seconds=int(metadata_stats.get("time_in_thermals_seconds") or 0),
        time_on_glide_seconds=int(metadata_stats.get("time_on_glide_seconds") or 0),
        total_track_distance_km=float(metadata_stats.get("total_track_distance_km") or 0),
        max_ground_speed_kmh=metadata_stats.get("max_ground_speed_kmh"),
    )


def _summary_payload(session: Session, flight: PilotFlight) -> LogbookFlightSummaryResponse:
    event = session.get(Event, flight.event_id) if flight.event_id else None
    task = session.get(Task, flight.task_id) if flight.task_id else None
    site = session.get(FlightSite, flight.site_id) if flight.site_id else None
    points = get_flight_track_points(session, flight)
    can_replay = bool(points)
    can_download = _trackbacked_download_path(session, flight) is not None
    return LogbookFlightSummaryResponse(
        id=flight.id,
        source_kind=flight.source_kind,
        flight_date=flight.flight_date,
        starred=bool(flight.starred),
        site_id=flight.site_id,
        site_name=flight.site_name or "",
        site_city_state=site.city_state if site else None,
        duration_seconds=flight.duration_seconds,
        highest_altitude_m=flight.highest_altitude_m,
        best_climb_mps=flight.best_climb_mps,
        event_name=event.name if event else None,
        task_name=task.name if task else None,
        filename=flight.filename,
        can_download=can_download,
        can_replay=can_replay,
        has_statistics=True,
    )


def _detail_payload(session: Session, flight: PilotFlight) -> LogbookFlightDetailResponse:
    summary = _summary_payload(session, flight)
    points = get_flight_track_points(session, flight)
    return LogbookFlightDetailResponse(
        **summary.model_dump(),
        notes=flight.notes,
        stats=_build_stats_payload(flight, points),
    )


def _folder_import_item_payload(item) -> LogbookFolderImportItemResponse:
    return LogbookFolderImportItemResponse(
        file_key=item.file_key,
        sha256=item.sha256,
        filename=item.filename,
        relative_path=item.relative_path,
        detected_pilot_name=item.detected_pilot_name,
        reason=item.reason,
        flight_id=item.flight_id,
    )


@router.get("/flights", response_model=list[LogbookFlightSummaryResponse])
def list_flights(user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[LogbookFlightSummaryResponse]:
    if user.pilot_id is None:
        return []
    flights = session.query(PilotFlight).filter(PilotFlight.pilot_id == user.pilot_id).order_by(PilotFlight.flight_date.desc(), PilotFlight.created_at.desc()).all()
    return [_summary_payload(session, flight) for flight in flights]


@router.post("/flights", response_model=LogbookFlightDetailResponse, status_code=status.HTTP_201_CREATED)
def create_manual_flight(payload: LogbookFlightCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> LogbookFlightDetailResponse:
    pilot_id = _require_pilot_profile(user)
    flight = PilotFlight(
        pilot_id=pilot_id,
        source_kind="manual",
        event_id=None,
        task_id=None,
        igc_upload_id=None,
        flight_date=payload.flight_date,
        site_name=payload.site_name.strip(),
        notes=payload.notes.strip() if payload.notes and payload.notes.strip() else None,
        duration_seconds=payload.duration_seconds,
        highest_altitude_m=payload.highest_altitude_m,
        best_climb_mps=payload.best_climb_mps,
        filename=None,
        sha256=None,
        stored_path=None,
        metadata_json={},
    )
    session.add(flight)
    session.commit()
    session.refresh(flight)
    return _detail_payload(session, flight)


@router.post("/flights/upload", response_model=LogbookFlightDetailResponse, status_code=status.HTTP_201_CREATED)
async def upload_logbook_flight(
    file: UploadFile = File(...),
    site_name: str | None = Form(default=None),
    notes: str | None = Form(default=None),
    flight_date: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LogbookFlightDetailResponse:
    _require_pilot_profile(user)
    content = await file.read()
    try:
        parsed_flight_date = date.fromisoformat(flight_date) if flight_date else None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Flight date must use YYYY-MM-DD format.") from exc
    flight = await create_app_upload_flight(
        session,
        user=user,
        filename=file.filename or "flight.igc",
        content=content,
        site_name=site_name,
        notes=notes,
        flight_date_override=parsed_flight_date,
    )
    session.commit()
    session.refresh(flight)
    return _detail_payload(session, flight)


@router.post("/flights/import-folder", response_model=LogbookFolderImportResponse)
async def import_logbook_folder(
    files: list[UploadFile] = File(...),
    relative_paths_json: str | None = Form(default=None),
    file_keys_json: str | None = Form(default=None),
    confirmed_file_keys_json: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LogbookFolderImportResponse:
    _require_pilot_profile(user)
    try:
        relative_paths = json.loads(relative_paths_json) if relative_paths_json else []
        file_keys = json.loads(file_keys_json) if file_keys_json else []
        confirmed_file_keys = set(json.loads(confirmed_file_keys_json)) if confirmed_file_keys_json else set()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder import metadata could not be parsed.") from exc

    if relative_paths and len(relative_paths) != len(files):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder import paths do not match the uploaded files.")
    if file_keys and len(file_keys) != len(files):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder import file keys do not match the uploaded files.")

    payload_files: list[tuple[str, str | None, bytes]] = []
    for index, file in enumerate(files):
        content = await file.read()
        relative_path = str(relative_paths[index]).strip() if relative_paths else None
        file_key = str(file_keys[index]).strip() if file_keys else (relative_path or file.filename or f"file-{index}")
        payload_files.append((file_key, relative_path, content))

    result = await import_logbook_folder_files(
        session,
        user=user,
        files=payload_files,
        confirmed_file_keys=confirmed_file_keys,
    )
    session.commit()
    return LogbookFolderImportResponse(
        imported=[_folder_import_item_payload(item) for item in result.imported],
        skipped=[_folder_import_item_payload(item) for item in result.skipped],
        review_needed=[_folder_import_item_payload(item) for item in result.review_needed],
    )


@router.post("/flights/{flight_id}/upload", response_model=LogbookFlightDetailResponse)
async def attach_logbook_flight_file(
    flight_id: int,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LogbookFlightDetailResponse:
    _require_pilot_profile(user)
    flight = _flight_for_user(session, user, flight_id)
    if flight.igc_upload_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Task-upload-backed flights already use their existing IGC file.")
    content = await file.read()
    flight = await attach_igc_to_existing_flight(
        session,
        flight=flight,
        filename=file.filename or "flight.igc",
        content=content,
    )
    session.commit()
    session.refresh(flight)
    return _detail_payload(session, flight)


@router.get("/flights/{flight_id}", response_model=LogbookFlightDetailResponse)
def get_flight(flight_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> LogbookFlightDetailResponse:
    flight = _flight_for_user(session, user, flight_id)
    return _detail_payload(session, flight)


@router.patch("/flights/{flight_id}", response_model=LogbookFlightDetailResponse)
def update_flight(
    flight_id: int,
    payload: LogbookFlightUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LogbookFlightDetailResponse:
    flight = _flight_for_user(session, user, flight_id)
    if payload.flight_date is not None:
        flight.flight_date = payload.flight_date
    if payload.site_name is not None:
        flight.site_name = payload.site_name.strip()
    if payload.notes is not None:
        flight.notes = payload.notes.strip() or None
    if payload.starred is not None:
        flight.starred = payload.starred
    if flight.source_kind == "manual":
        if payload.duration_seconds is not None:
            flight.duration_seconds = payload.duration_seconds
        if payload.highest_altitude_m is not None:
            flight.highest_altitude_m = payload.highest_altitude_m
        if payload.best_climb_mps is not None:
            flight.best_climb_mps = payload.best_climb_mps
    session.add(flight)
    session.commit()
    session.refresh(flight)
    return _detail_payload(session, flight)


@router.get("/flights/{flight_id}/track")
def get_flight_track(
    flight_id: int,
    detail: str = Query(default="replay"),
    max_points: int = Query(default=DEFAULT_REPLAY_MAX_POINTS, ge=2, le=100000),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    flight = _flight_for_user(session, user, flight_id)
    points = get_flight_track_points(session, flight)
    if not points:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This flight does not have replayable track data.")
    task_id = flight.task_id
    if task_id is None and flight.igc_upload_id is not None:
        upload = session.get(IGCUpload, flight.igc_upload_id)
        task_id = upload.task_id if upload is not None else None
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == task_id).order_by(TaskPoint.position)).all() if task_id is not None else []
    simplified = simplify_replay_points(points, task_points=task_points, max_points=max_points) if detail != "full" else None
    replay_points = simplified.points if simplified is not None else points
    pilot_name = user.full_name or "Pilot"
    coordinates = [
        [
            point.longitude,
            point.latitude,
            float(point.gps_altitude_m if point.gps_altitude_m is not None else point.pressure_altitude_m if point.pressure_altitude_m is not None else 0),
        ]
        for point in replay_points
    ]
    timestamps = [point.recorded_at.isoformat().replace("+00:00", "Z") for point in replay_points]
    return {
        "type": "FeatureCollection",
        "metadata": {
            "detail": "full" if detail == "full" else "replay",
            "original_point_count": len(points),
            "returned_point_count": len(replay_points),
            "max_points": max_points,
            "simplified": simplified.simplified if simplified is not None else False,
            "task_aware": simplified.task_aware if simplified is not None else bool(task_points),
        },
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "upload_id": flight.id,
                    "pilot_name": pilot_name,
                    "aircraft_icon": (user.aircraft_icon or "hang_glider").strip().lower(),
                    "timestamps": timestamps,
                },
                "geometry": {"type": "LineString", "coordinates": coordinates},
            }
        ],
    }


@router.get("/flights/{flight_id}/download")
def download_flight_igc(flight_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> FileResponse:
    flight = _flight_for_user(session, user, flight_id)
    stored_path = _trackbacked_download_path(session, flight)
    if stored_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This flight does not have a downloadable IGC file.")
    filename = flight.filename or stored_path.name
    return FileResponse(path=stored_path, media_type="application/octet-stream", filename=filename)


@router.delete("/flights", response_model=LogbookBulkDeleteResponse)
def bulk_delete_flights(
    payload: LogbookBulkDeleteRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> LogbookBulkDeleteResponse:
    pilot_id = _require_pilot_profile(user)
    requested_ids = list(dict.fromkeys(payload.flight_ids))
    if not requested_ids:
        return LogbookBulkDeleteResponse(deleted_ids=[], deleted_count=0)

    flights = (
        session.query(PilotFlight)
        .filter(PilotFlight.pilot_id == pilot_id, PilotFlight.id.in_(requested_ids))
        .all()
    )
    found_ids = {flight.id for flight in flights}
    missing_ids = [flight_id for flight_id in requested_ids if flight_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more flights were not found.")

    cleanup_paths: list[str | None] = []
    for flight in flights:
        cleanup_paths.extend(_delete_flight_records(session, user, flight))
    session.commit()
    for stored_path in cleanup_paths:
        _cleanup_stored_file(stored_path)
    return LogbookBulkDeleteResponse(deleted_ids=requested_ids, deleted_count=len(requested_ids))


@router.delete("/flights/{flight_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_flight(flight_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> None:
    flight = _flight_for_user(session, user, flight_id)
    cleanup_paths = _delete_flight_records(session, user, flight)
    session.commit()
    for stored_path in cleanup_paths:
        _cleanup_stored_file(stored_path)
