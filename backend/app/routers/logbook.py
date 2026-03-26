from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user
from app.models import Event, IGCUpload, PilotFlight, PilotFlightTrackPoint, Task, TrackPoint, User
from app.schemas import LogbookFlightCreate, LogbookFlightDetailResponse, LogbookFlightStatsResponse, LogbookFlightSummaryResponse, LogbookFlightUpdate
from app.services.logbook import create_app_upload_flight, derive_flight_stats, get_flight_track_points

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
            fix_count=stats.fix_count,
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
        fix_count=int(metadata_stats.get("fix_count") or 0),
        total_track_distance_km=float(metadata_stats.get("total_track_distance_km") or 0),
        max_ground_speed_kmh=metadata_stats.get("max_ground_speed_kmh"),
    )


def _summary_payload(session: Session, flight: PilotFlight) -> LogbookFlightSummaryResponse:
    event = session.get(Event, flight.event_id) if flight.event_id else None
    task = session.get(Task, flight.task_id) if flight.task_id else None
    points = get_flight_track_points(session, flight)
    can_replay = bool(points)
    can_download = _trackbacked_download_path(session, flight) is not None
    return LogbookFlightSummaryResponse(
        id=flight.id,
        source_kind=flight.source_kind,
        flight_date=flight.flight_date,
        site_name=flight.site_name or "",
        duration_seconds=flight.duration_seconds,
        highest_altitude_m=flight.highest_altitude_m,
        best_climb_mps=flight.best_climb_mps,
        event_name=event.name if event else None,
        task_name=task.name if task else None,
        filename=flight.filename,
        can_download=can_download,
        can_replay=can_replay,
        has_statistics=bool(
            flight.duration_seconds is not None
            or flight.highest_altitude_m is not None
            or flight.best_climb_mps is not None
            or points
        ),
    )


def _detail_payload(session: Session, flight: PilotFlight) -> LogbookFlightDetailResponse:
    summary = _summary_payload(session, flight)
    points = get_flight_track_points(session, flight)
    return LogbookFlightDetailResponse(
        **summary.model_dump(),
        notes=flight.notes,
        stats=_build_stats_payload(flight, points),
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
def get_flight_track(flight_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    flight = _flight_for_user(session, user, flight_id)
    points = get_flight_track_points(session, flight)
    if not points:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This flight does not have replayable track data.")
    pilot_name = user.full_name or "Pilot"
    coordinates = [
        [
            point.longitude,
            point.latitude,
            float(point.gps_altitude_m if point.gps_altitude_m is not None else point.pressure_altitude_m if point.pressure_altitude_m is not None else 0),
        ]
        for point in points
    ]
    timestamps = [point.recorded_at.isoformat().replace("+00:00", "Z") for point in points]
    return {
        "type": "FeatureCollection",
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
