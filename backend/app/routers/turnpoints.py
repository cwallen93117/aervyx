from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import Event, EventTurnpointSlot, TaskPoint, Turnpoint, TurnpointSource, User
from app.schemas import (
    TurnpointResponse,
    TurnpointSourceMerge,
    TurnpointSourceResponse,
    TurnpointSourceSaveAs,
    TurnpointSourceUpdate,
    TurnpointUploadResponse,
    TurnpointWrite,
)
from app.services.audit import log_action
from app.services.event_access import require_event_manager
from app.services.turnpoints import (
    TurnpointRecord,
    normalize_symbol,
    parse_turnpoint_upload,
    rewrite_turnpoint_source_file,
    serialize_csv_turnpoints,
    serialize_geojson_turnpoints,
    serialize_gpx_turnpoints,
    validate_coordinate,
)
from app.services.waypoint_access import can_view_waypoints

router = APIRouter(tags=["turnpoints"])
SUPPORTED_FORMATS = {"csv", "gpx", "geojson"}


def _source_payload(session: Session, source: TurnpointSource) -> TurnpointSourceResponse:
    count = session.scalar(select(func.count()).select_from(Turnpoint).where(Turnpoint.source_id == source.id)) or 0
    return TurnpointSourceResponse(
        id=source.id,
        filename=source.filename,
        file_format=source.file_format,
        sha256=source.sha256,
        turnpoint_count=count,
    )


def _source_turnpoints(session: Session, source: TurnpointSource) -> list[Turnpoint]:
    return list(
        session.scalars(
            select(Turnpoint)
            .where(Turnpoint.source_id == source.id)
            .order_by(Turnpoint.source_row_index.asc(), Turnpoint.id.asc())
        ).all()
    )


def _turnpoint_response(turnpoint: Turnpoint) -> TurnpointResponse:
    payload = TurnpointResponse.model_validate(turnpoint)
    payload.extra_json = turnpoint.extra_json or {}
    return payload


def _library_source_or_404(session: Session, source_id: int) -> TurnpointSource:
    source = session.get(TurnpointSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Turnpoint library file not found")
    return source


def _event_or_404(session: Session, event_id: int, user: User) -> Event:
    event = session.get(Event, event_id)
    if event is None or not can_view_waypoints(session, user, event):
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _event_source_or_404(session: Session, event_id: int, source_id: int, user: User) -> TurnpointSource:
    _event_or_404(session, event_id, user)
    slot = session.scalar(
        select(EventTurnpointSlot).where(
            EventTurnpointSlot.event_id == event_id,
            EventTurnpointSlot.source_id == source_id,
        )
    )
    if slot is None:
        raise HTTPException(status_code=404, detail="Turnpoint source not selected for this event")
    return _library_source_or_404(session, source_id)


def _clean_source_filename(filename: str, file_format: str) -> str:
    if file_format not in SUPPORTED_FORMATS:
        raise HTTPException(status_code=400, detail="Format must be csv, gpx, or geojson.")
    cleaned = filename.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Filename is required.")
    if Path(cleaned).name != cleaned or "/" in cleaned or "\\" in cleaned:
        raise HTTPException(status_code=400, detail="Filename must not include folders.")
    extension = ".geojson" if file_format == "geojson" else f".{file_format}"
    path = Path(cleaned)
    cleaned = f"{path.stem if path.suffix else cleaned}{extension}"
    return cleaned[:255]


def _record(turnpoint: Turnpoint) -> TurnpointRecord:
    return TurnpointRecord(
        name=turnpoint.name,
        code=turnpoint.code,
        latitude=turnpoint.latitude,
        longitude=turnpoint.longitude,
        elevation_m=turnpoint.elevation_m,
        symbol=normalize_symbol(turnpoint.symbol),
        extra_json=turnpoint.extra_json or {},
        source_row_index=turnpoint.source_row_index,
    )


def _serialize_records(records: list[TurnpointRecord], file_format: str, schema: dict | None = None) -> bytes:
    schema = schema or {}
    if file_format == "csv":
        return serialize_csv_turnpoints(records, schema).encode("utf-8")
    if file_format == "gpx":
        return serialize_gpx_turnpoints(records, schema).encode("utf-8")
    if file_format == "geojson":
        return serialize_geojson_turnpoints(records, schema).encode("utf-8")
    raise HTTPException(status_code=400, detail="Format must be csv, gpx, or geojson.")


def _create_library_source(
    session: Session,
    *,
    filename: str,
    file_format: str,
    content_type: str | None,
    schema: dict | None,
    records: list[TurnpointRecord],
    content: bytes | None = None,
) -> tuple[TurnpointSource, Path]:
    filename = _clean_source_filename(filename, file_format)
    content = content if content is not None else _serialize_records(records, file_format, schema)
    sha256 = hashlib.sha256(content).hexdigest()
    stored_path = Path(get_settings().upload_root) / "turnpoints" / f"library-{uuid.uuid4().hex}" / filename
    stored_path.parent.mkdir(parents=True, exist_ok=False)
    stored_path.write_bytes(content)
    source = TurnpointSource(
        event_id=None,
        filename=filename,
        content_type=content_type,
        file_format=file_format,
        sha256=sha256,
        stored_path=str(stored_path),
        schema_json=schema or {},
        enabled=True,
    )
    session.add(source)
    session.flush()
    for index, item in enumerate(records):
        session.add(
            Turnpoint(
                event_id=None,
                source_id=source.id,
                code=item.code,
                symbol=item.symbol,
                name=item.name,
                latitude=item.latitude,
                longitude=item.longitude,
                elevation_m=item.elevation_m,
                extra_json=item.extra_json,
                source_row_index=item.source_row_index if item.source_row_index is not None else index,
            )
        )
    session.flush()
    return source, stored_path


def _cleanup_new_file(path: Path | None) -> None:
    if path is None:
        return
    path.unlink(missing_ok=True)
    if path.parent.exists() and not any(path.parent.iterdir()):
        path.parent.rmdir()


def _apply_turnpoint_payload(turnpoint: Turnpoint, payload: TurnpointWrite) -> None:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Waypoint name is required.")
    try:
        validate_coordinate(payload.latitude, payload.longitude)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    symbol = normalize_symbol(payload.symbol)
    if payload.symbol and not symbol:
        raise HTTPException(status_code=400, detail="Unsupported waypoint symbol.")
    turnpoint.name = name
    turnpoint.code = payload.code.strip()[:40] if payload.code and payload.code.strip() else None
    turnpoint.symbol = symbol
    turnpoint.latitude = payload.latitude
    turnpoint.longitude = payload.longitude
    turnpoint.elevation_m = payload.elevation_m
    turnpoint.extra_json = payload.extra_json or {}


@router.get("/api/turnpoint-library", response_model=list[TurnpointSourceResponse])
def list_turnpoint_library(_staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[TurnpointSourceResponse]:
    sources = session.scalars(select(TurnpointSource).order_by(TurnpointSource.uploaded_at.desc(), TurnpointSource.id.desc())).all()
    return [_source_payload(session, source) for source in sources]


@router.post("/api/turnpoint-library/upload", response_model=TurnpointUploadResponse)
async def upload_turnpoint_library_file(
    file: UploadFile = File(...),
    staff: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> TurnpointUploadResponse:
    content = await file.read()
    parsed = parse_turnpoint_upload(file.filename or "turnpoints.gpx", content)
    stored_path: Path | None = None
    try:
        source, stored_path = _create_library_source(
            session,
            filename=file.filename or f"turnpoints.{parsed.file_format}",
            file_format=parsed.file_format,
            content_type=file.content_type,
            schema=parsed.schema_json,
            records=parsed.records,
            content=content,
        )
        log_action(session, actor_user_id=staff.id, action="turnpoint_library.upload", entity_type="turnpoint_source", entity_id=str(source.id), details={"filename": source.filename, "count": len(parsed.records)})
        session.commit()
        return TurnpointUploadResponse(source_id=source.id, format=source.file_format, imported_count=len(parsed.records), sha256=source.sha256, filename=source.filename)
    except Exception:
        session.rollback()
        _cleanup_new_file(stored_path)
        raise


@router.get("/api/turnpoint-library/{source_id}/turnpoints", response_model=list[TurnpointResponse])
def list_library_turnpoints(source_id: int, _staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    source = _library_source_or_404(session, source_id)
    return [_turnpoint_response(point) for point in _source_turnpoints(session, source)]


@router.get("/api/turnpoint-library/{source_id}/download")
def download_library_file(source_id: int, _staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> FileResponse:
    source = _library_source_or_404(session, source_id)
    stored_path = Path(source.stored_path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Stored turnpoint file not found")
    media_type = {"csv": "text/csv", "gpx": "application/gpx+xml", "geojson": "application/geo+json"}.get(source.file_format, "application/octet-stream")
    return FileResponse(stored_path, filename=source.filename, media_type=media_type)


@router.post("/api/turnpoint-library/{source_id}/turnpoints", response_model=TurnpointResponse)
def create_library_turnpoint(source_id: int, payload: TurnpointWrite, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointResponse:
    source = _library_source_or_404(session, source_id)
    existing = _source_turnpoints(session, source)
    point = Turnpoint(event_id=None, source_id=source.id, name="", latitude=0, longitude=0, source_row_index=len(existing))
    _apply_turnpoint_payload(point, payload)
    session.add(point)
    session.flush()
    rewrite_turnpoint_source_file(source, _source_turnpoints(session, source))
    log_action(session, actor_user_id=staff.id, action="turnpoint_library.create_waypoint", entity_type="turnpoint", entity_id=str(point.id), details={"source_id": source.id})
    session.commit()
    session.refresh(point)
    return _turnpoint_response(point)


@router.put("/api/turnpoint-library/{source_id}/turnpoints/{turnpoint_id}", response_model=TurnpointResponse)
def update_library_turnpoint(source_id: int, turnpoint_id: int, payload: TurnpointWrite, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointResponse:
    source = _library_source_or_404(session, source_id)
    point = session.get(Turnpoint, turnpoint_id)
    if point is None or point.source_id != source.id:
        raise HTTPException(status_code=404, detail="Turnpoint not found")
    _apply_turnpoint_payload(point, payload)
    session.flush()
    rewrite_turnpoint_source_file(source, _source_turnpoints(session, source))
    log_action(session, actor_user_id=staff.id, action="turnpoint_library.update_waypoint", entity_type="turnpoint", entity_id=str(point.id), details={"source_id": source.id})
    session.commit()
    session.refresh(point)
    return _turnpoint_response(point)


@router.delete("/api/turnpoint-library/{source_id}/turnpoints/{turnpoint_id}", status_code=204)
def delete_library_turnpoint(source_id: int, turnpoint_id: int, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    source = _library_source_or_404(session, source_id)
    point = session.get(Turnpoint, turnpoint_id)
    if point is None or point.source_id != source.id:
        raise HTTPException(status_code=404, detail="Turnpoint not found")
    session.query(TaskPoint).filter(TaskPoint.turnpoint_id == point.id).update({TaskPoint.turnpoint_id: None}, synchronize_session=False)
    session.delete(point)
    session.flush()
    remaining = _source_turnpoints(session, source)
    for index, item in enumerate(remaining):
        item.source_row_index = index
    rewrite_turnpoint_source_file(source, remaining)
    log_action(session, actor_user_id=staff.id, action="turnpoint_library.delete_waypoint", entity_type="turnpoint", entity_id=str(turnpoint_id), details={"source_id": source.id})
    session.commit()


@router.patch("/api/turnpoint-library/{source_id}", response_model=TurnpointSourceResponse)
def update_library_source(source_id: int, payload: TurnpointSourceUpdate, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    source = _library_source_or_404(session, source_id)
    if payload.filename is None:
        raise HTTPException(status_code=400, detail="Filename is required.")
    source.filename = _clean_source_filename(payload.filename, source.file_format)
    log_action(session, actor_user_id=staff.id, action="turnpoint_library.rename", entity_type="turnpoint_source", entity_id=str(source.id), details={"filename": source.filename})
    session.commit()
    session.refresh(source)
    return _source_payload(session, source)


@router.post("/api/turnpoint-library/{source_id}/save-as", response_model=TurnpointSourceResponse)
def save_library_source_as(source_id: int, payload: TurnpointSourceSaveAs, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    source = _library_source_or_404(session, source_id)
    file_format = (payload.file_format or source.file_format).strip().lower()
    records = [_record(point) for point in _source_turnpoints(session, source)]
    schema = source.schema_json if file_format == source.file_format else {}
    stored_path: Path | None = None
    try:
        duplicate, stored_path = _create_library_source(
            session,
            filename=payload.filename,
            file_format=file_format,
            content_type={"csv": "text/csv", "gpx": "application/gpx+xml", "geojson": "application/geo+json"}.get(file_format),
            schema=schema,
            records=records,
        )
        log_action(session, actor_user_id=staff.id, action="turnpoint_library.save_as", entity_type="turnpoint_source", entity_id=str(duplicate.id), details={"source_id": source.id, "filename": duplicate.filename, "format": file_format})
        session.commit()
        session.refresh(duplicate)
        return _source_payload(session, duplicate)
    except Exception:
        session.rollback()
        _cleanup_new_file(stored_path)
        raise


@router.post("/api/turnpoint-library/merge", response_model=TurnpointSourceResponse)
def merge_library_sources(payload: TurnpointSourceMerge, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    if len(payload.source_ids) < 2 or len(set(payload.source_ids)) != len(payload.source_ids):
        raise HTTPException(status_code=400, detail="Select at least two distinct turnpoint files.")
    sources_by_id = {source.id: source for source in session.scalars(select(TurnpointSource).where(TurnpointSource.id.in_(payload.source_ids))).all()}
    if len(sources_by_id) != len(payload.source_ids):
        raise HTTPException(status_code=404, detail="One or more turnpoint library files were not found.")
    records: list[TurnpointRecord] = []
    seen: set[tuple[str, str, float, float]] = set()
    for source_id in payload.source_ids:
        for point in _source_turnpoints(session, sources_by_id[source_id]):
            key = (
                point.name.strip().casefold(),
                (point.code or "").strip().casefold(),
                round(point.latitude, 6),
                round(point.longitude, 6),
            )
            if key in seen:
                continue
            seen.add(key)
            records.append(_record(point))
    stored_path: Path | None = None
    try:
        merged, stored_path = _create_library_source(
            session,
            filename=payload.filename,
            file_format="gpx",
            content_type="application/gpx+xml",
            schema={},
            records=records,
        )
        log_action(session, actor_user_id=staff.id, action="turnpoint_library.merge", entity_type="turnpoint_source", entity_id=str(merged.id), details={"source_ids": payload.source_ids, "filename": merged.filename, "count": len(records)})
        session.commit()
        session.refresh(merged)
        return _source_payload(session, merged)
    except Exception:
        session.rollback()
        _cleanup_new_file(stored_path)
        raise


@router.delete("/api/turnpoint-library/{source_id}", status_code=204)
def delete_library_source(source_id: int, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    source = _library_source_or_404(session, source_id)
    filename = source.filename
    stored_path = Path(source.stored_path)
    shared_path = session.scalar(select(func.count()).select_from(TurnpointSource).where(TurnpointSource.stored_path == source.stored_path, TurnpointSource.id != source.id)) or 0
    session.query(EventTurnpointSlot).filter(EventTurnpointSlot.source_id == source.id).delete(synchronize_session=False)
    session.query(TaskPoint).filter(TaskPoint.turnpoint_id.in_(select(Turnpoint.id).where(Turnpoint.source_id == source.id))).update({TaskPoint.turnpoint_id: None}, synchronize_session=False)
    session.query(Turnpoint).filter(Turnpoint.source_id == source.id).delete(synchronize_session=False)
    session.delete(source)
    log_action(session, actor_user_id=staff.id, action="turnpoint_library.delete", entity_type="turnpoint_source", entity_id=str(source_id), details={"filename": filename})
    session.commit()
    if not shared_path:
        _cleanup_new_file(stored_path)


@router.get("/api/events/{event_id}/turnpoints", response_model=list[TurnpointResponse])
def list_turnpoints(event_id: int, search: str | None = Query(default=None), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    _event_or_404(session, event_id, user)
    selected_source_ids = list(session.scalars(select(EventTurnpointSlot.source_id).where(EventTurnpointSlot.event_id == event_id)).all())
    query = select(Turnpoint).where(
        or_(
            Turnpoint.source_id.in_(selected_source_ids),
            (Turnpoint.source_id.is_(None) & (Turnpoint.event_id == event_id)),
        )
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Turnpoint.name.ilike(pattern), Turnpoint.code.ilike(pattern)))
    return [_turnpoint_response(point) for point in session.scalars(query.order_by(Turnpoint.name.asc())).all()]


@router.get("/api/events/{event_id}/turnpoint-sources", response_model=list[TurnpointSourceResponse])
def list_turnpoint_sources(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointSourceResponse]:
    _event_or_404(session, event_id, user)
    sources = session.scalars(
        select(TurnpointSource)
        .join(EventTurnpointSlot, EventTurnpointSlot.source_id == TurnpointSource.id)
        .where(EventTurnpointSlot.event_id == event_id)
        .order_by(EventTurnpointSlot.slot_number.asc())
    ).all()
    return [_source_payload(session, source) for source in sources]


@router.post("/api/events/{event_id}/turnpoint-sources/{source_id}", response_model=TurnpointSourceResponse)
def select_event_turnpoint_source(event_id: int, source_id: int, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    require_event_manager(session, staff, session.get(Event, event_id))
    source = _library_source_or_404(session, source_id)
    existing = session.scalar(select(EventTurnpointSlot).where(EventTurnpointSlot.event_id == event_id, EventTurnpointSlot.source_id == source_id))
    if existing is None:
        session.add(EventTurnpointSlot(event_id=event_id, slot_number=source_id, source_id=source_id))
        log_action(session, actor_user_id=staff.id, action="event.turnpoint_library.select", entity_type="event", entity_id=str(event_id), details={"source_id": source_id})
        session.commit()
    return _source_payload(session, source)


@router.delete("/api/events/{event_id}/turnpoint-sources/{source_id}", status_code=204)
def deselect_event_turnpoint_source(event_id: int, source_id: int, staff: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    require_event_manager(session, staff, session.get(Event, event_id))
    slot = session.scalar(select(EventTurnpointSlot).where(EventTurnpointSlot.event_id == event_id, EventTurnpointSlot.source_id == source_id))
    if slot is None:
        raise HTTPException(status_code=404, detail="Turnpoint source not selected for this event")
    session.delete(slot)
    log_action(session, actor_user_id=staff.id, action="event.turnpoint_library.deselect", entity_type="event", entity_id=str(event_id), details={"source_id": source_id})
    session.commit()


@router.get("/api/events/{event_id}/turnpoint-sources/{source_id}/turnpoints", response_model=list[TurnpointResponse])
def list_source_turnpoints(event_id: int, source_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    source = _event_source_or_404(session, event_id, source_id, user)
    return [_turnpoint_response(point) for point in _source_turnpoints(session, source)]
