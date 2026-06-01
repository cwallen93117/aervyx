from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import false, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import Event, TaskPoint, Turnpoint, TurnpointSource, User
from app.schemas import TurnpointResponse, TurnpointSourceResponse, TurnpointSourceSaveAs, TurnpointSourceUpdate, TurnpointUploadResponse, TurnpointWrite
from app.services.audit import log_action
from app.services.turnpoints import normalize_symbol, rewrite_turnpoint_source_file, validate_coordinate, parse_turnpoint_upload

router = APIRouter(tags=["turnpoints"])


def _source_payload(session: Session, source: TurnpointSource) -> TurnpointSourceResponse:
    turnpoint_count = session.scalar(select(func.count()).select_from(Turnpoint).where(Turnpoint.source_id == source.id)) or 0
    return TurnpointSourceResponse(
        id=source.id,
        event_id=source.event_id,
        filename=source.filename,
        file_format=source.file_format,
        sha256=source.sha256,
        enabled=source.enabled,
        uploaded_at=source.uploaded_at,
        turnpoint_count=turnpoint_count,
    )


def _enabled_source_ids(session: Session, event_id: int) -> list[int]:
    return list(
        session.scalars(
            select(TurnpointSource.id).where(
                TurnpointSource.event_id == event_id,
                TurnpointSource.enabled.is_(True),
            )
        ).all()
    )


def _delete_task_points_for_turnpoints(session: Session, turnpoint_ids: list[int]) -> None:
    if not turnpoint_ids:
        return
    session.query(TaskPoint).filter(TaskPoint.turnpoint_id.in_(turnpoint_ids)).delete(synchronize_session=False)


def _delete_legacy_unsourced_turnpoints(session: Session, event_id: int) -> None:
    legacy_turnpoint_ids = list(
        session.scalars(
            select(Turnpoint.id).where(
                Turnpoint.event_id == event_id,
                Turnpoint.source_id.is_(None),
            )
        ).all()
    )
    _delete_task_points_for_turnpoints(session, legacy_turnpoint_ids)
    if legacy_turnpoint_ids:
        session.query(Turnpoint).filter(Turnpoint.id.in_(legacy_turnpoint_ids)).delete(synchronize_session=False)


@router.get("/api/events/{event_id}/turnpoints", response_model=list[TurnpointResponse])
def list_turnpoints(event_id: int, search: str | None = Query(default=None), user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    query = select(Turnpoint).where(Turnpoint.event_id == event_id)
    source_ids = list(session.scalars(select(TurnpointSource.id).where(TurnpointSource.event_id == event_id)).all())
    enabled_source_ids = _enabled_source_ids(session, event_id)
    if source_ids:
        query = query.where(Turnpoint.source_id.in_(enabled_source_ids)) if enabled_source_ids else query.where(false())
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(Turnpoint.name.ilike(pattern), Turnpoint.code.ilike(pattern)))
    turnpoints = session.scalars(query.order_by(Turnpoint.name.asc())).all()
    return [_turnpoint_response(turnpoint) for turnpoint in turnpoints]


@router.get("/api/events/{event_id}/turnpoint-sources", response_model=list[TurnpointSourceResponse])
def list_turnpoint_sources(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointSourceResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    sources = session.scalars(select(TurnpointSource).where(TurnpointSource.event_id == event_id).order_by(TurnpointSource.uploaded_at.desc(), TurnpointSource.id.desc())).all()
    return [_source_payload(session, source) for source in sources]


def _source_or_404(session: Session, event_id: int, source_id: int) -> TurnpointSource:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    source = session.get(TurnpointSource, source_id)
    if source is None or source.event_id != event_id:
        raise HTTPException(status_code=404, detail="Turnpoint source not found")
    return source


def _source_turnpoints(session: Session, source: TurnpointSource) -> list[Turnpoint]:
    return list(session.scalars(select(Turnpoint).where(Turnpoint.source_id == source.id).order_by(Turnpoint.source_row_index.asc(), Turnpoint.id.asc())).all())


def _clean_source_filename(filename: str, file_format: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Filename is required.")
    if Path(cleaned).name != cleaned or "/" in cleaned or "\\" in cleaned:
        raise HTTPException(status_code=400, detail="Filename must not include folders.")
    suffix = Path(cleaned).suffix.lower()
    if not suffix:
        extension = ".geojson" if file_format == "geojson" else f".{file_format}"
        cleaned = f"{cleaned}{extension}"
    return cleaned[:255]


def _turnpoint_response(turnpoint: Turnpoint) -> TurnpointResponse:
    payload = TurnpointResponse.model_validate(turnpoint)
    payload.extra_json = turnpoint.extra_json or {}
    return payload


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


@router.get("/api/events/{event_id}/turnpoint-sources/{source_id}/turnpoints", response_model=list[TurnpointResponse])
def list_source_turnpoints(event_id: int, source_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[TurnpointResponse]:
    source = _source_or_404(session, event_id, source_id)
    return [_turnpoint_response(turnpoint) for turnpoint in _source_turnpoints(session, source)]


@router.get("/api/events/{event_id}/turnpoint-sources/{source_id}/download")
def download_turnpoint_source(event_id: int, source_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> FileResponse:
    source = _source_or_404(session, event_id, source_id)
    stored_path = Path(source.stored_path)
    if not stored_path.exists():
        raise HTTPException(status_code=404, detail="Stored turnpoint file not found")
    media_type = {
        "csv": "text/csv",
        "gpx": "application/gpx+xml",
        "geojson": "application/geo+json",
    }.get(source.file_format, "application/octet-stream")
    return FileResponse(stored_path, filename=source.filename, media_type=media_type)


@router.post("/api/events/{event_id}/turnpoint-sources/{source_id}/turnpoints", response_model=TurnpointResponse)
def create_source_turnpoint(event_id: int, source_id: int, payload: TurnpointWrite, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointResponse:
    source = _source_or_404(session, event_id, source_id)
    existing = _source_turnpoints(session, source)
    next_row_index = max((turnpoint.source_row_index or 0 for turnpoint in existing), default=-1) + 1
    turnpoint = Turnpoint(event_id=event_id, source_id=source.id, name="", latitude=0, longitude=0, source_row_index=next_row_index)
    _apply_turnpoint_payload(turnpoint, payload)
    session.add(turnpoint)
    session.flush()
    rewrite_turnpoint_source_file(source, _source_turnpoints(session, source))
    log_action(session, actor_user_id=admin.id, action="turnpoint.create", entity_type="turnpoint", entity_id=str(turnpoint.id), details={"event_id": event_id, "source_id": source.id, "filename": source.filename})
    session.commit()
    session.refresh(turnpoint)
    return _turnpoint_response(turnpoint)


@router.put("/api/events/{event_id}/turnpoints/{turnpoint_id}", response_model=TurnpointResponse)
def update_turnpoint(event_id: int, turnpoint_id: int, payload: TurnpointWrite, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    turnpoint = session.get(Turnpoint, turnpoint_id)
    if turnpoint is None or turnpoint.event_id != event_id or turnpoint.source_id is None:
        raise HTTPException(status_code=404, detail="Turnpoint not found")
    source = _source_or_404(session, event_id, turnpoint.source_id)
    _apply_turnpoint_payload(turnpoint, payload)
    session.flush()
    rewrite_turnpoint_source_file(source, _source_turnpoints(session, source))
    log_action(session, actor_user_id=admin.id, action="turnpoint.update", entity_type="turnpoint", entity_id=str(turnpoint.id), details={"event_id": event_id, "source_id": source.id, "filename": source.filename})
    session.commit()
    session.refresh(turnpoint)
    return _turnpoint_response(turnpoint)


@router.delete("/api/events/{event_id}/turnpoints/{turnpoint_id}", status_code=204)
def delete_turnpoint(event_id: int, turnpoint_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    turnpoint = session.get(Turnpoint, turnpoint_id)
    if turnpoint is None or turnpoint.event_id != event_id or turnpoint.source_id is None:
        raise HTTPException(status_code=404, detail="Turnpoint not found")
    source = _source_or_404(session, event_id, turnpoint.source_id)
    _delete_task_points_for_turnpoints(session, [turnpoint.id])
    session.delete(turnpoint)
    session.flush()
    remaining = _source_turnpoints(session, source)
    for index, item in enumerate(remaining):
        item.source_row_index = index
    rewrite_turnpoint_source_file(source, remaining)
    log_action(session, actor_user_id=admin.id, action="turnpoint.delete-row", entity_type="turnpoint", entity_id=str(turnpoint_id), details={"event_id": event_id, "source_id": source.id, "filename": source.filename})
    session.commit()


@router.post("/api/events/{event_id}/turnpoint-sources/{source_id}/save-as", response_model=TurnpointSourceResponse)
def save_turnpoint_source_as(event_id: int, source_id: int, payload: TurnpointSourceSaveAs, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    source = _source_or_404(session, event_id, source_id)
    filename = _clean_source_filename(payload.filename, source.file_format)
    settings = get_settings()
    stored_path = Path(settings.upload_root) / "turnpoints" / f"version-{uuid.uuid4().hex}" / filename
    duplicate = TurnpointSource(
        event_id=event_id,
        filename=filename,
        content_type=source.content_type,
        file_format=source.file_format,
        sha256=source.sha256,
        stored_path=str(stored_path),
        schema_json=source.schema_json,
        enabled=source.enabled,
    )
    session.add(duplicate)
    session.flush()
    for turnpoint in _source_turnpoints(session, source):
        session.add(
            Turnpoint(
                event_id=event_id,
                source_id=duplicate.id,
                code=turnpoint.code,
                symbol=turnpoint.symbol,
                name=turnpoint.name,
                latitude=turnpoint.latitude,
                longitude=turnpoint.longitude,
                elevation_m=turnpoint.elevation_m,
                extra_json=turnpoint.extra_json,
                source_row_index=turnpoint.source_row_index,
            )
        )
    session.flush()
    rewrite_turnpoint_source_file(duplicate, _source_turnpoints(session, duplicate))
    log_action(session, actor_user_id=admin.id, action="turnpoint.save_as", entity_type="turnpoint_source", entity_id=str(duplicate.id), details={"event_id": event_id, "source_id": source.id, "filename": filename})
    session.commit()
    session.refresh(duplicate)
    return _source_payload(session, duplicate)


@router.post("/api/events/{event_id}/turnpoints/upload", response_model=TurnpointUploadResponse)
async def upload_turnpoints(event_id: int, file: UploadFile = File(...), admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointUploadResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    parsed = parse_turnpoint_upload(file.filename or "turnpoints.csv", content)
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "turnpoints" / sha256
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (file.filename or f"turnpoints.{file_format}")
    if not stored_path.exists():
        stored_path.write_bytes(content)
    source = TurnpointSource(
        event_id=event_id,
        filename=file.filename or stored_path.name,
        content_type=file.content_type,
        file_format=parsed.file_format,
        sha256=sha256,
        stored_path=str(stored_path),
        schema_json=parsed.schema_json,
        enabled=True,
    )
    session.add(source)
    session.flush()
    for index, record in enumerate(parsed.records):
        session.add(
            Turnpoint(
                event_id=event_id,
                source_id=source.id,
                code=record.code,
                symbol=record.symbol,
                name=record.name,
                latitude=record.latitude,
                longitude=record.longitude,
                elevation_m=record.elevation_m,
                extra_json=record.extra_json,
                source_row_index=record.source_row_index if record.source_row_index is not None else index,
            )
        )
    _delete_legacy_unsourced_turnpoints(session, event_id)
    log_action(session, actor_user_id=admin.id, action="turnpoint.upload", entity_type="turnpoint_source", entity_id=str(source.id), details={"event_id": event_id, "filename": source.filename, "sha256": sha256, "count": len(parsed.records)})
    session.commit()
    return TurnpointUploadResponse(source_id=source.id, format=parsed.file_format, imported_count=len(parsed.records), sha256=sha256, filename=source.filename)


@router.patch("/api/events/{event_id}/turnpoint-sources/{source_id}", response_model=TurnpointSourceResponse)
def update_turnpoint_source(event_id: int, source_id: int, payload: TurnpointSourceUpdate, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> TurnpointSourceResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    source = session.get(TurnpointSource, source_id)
    if source is None or source.event_id != event_id:
        raise HTTPException(status_code=404, detail="Turnpoint source not found")
    details: dict[str, object] = {"event_id": event_id, "filename": source.filename}
    if payload.enabled is not None:
        source.enabled = payload.enabled
        details["enabled"] = payload.enabled
    if payload.filename is not None:
        source.filename = _clean_source_filename(payload.filename, source.file_format)
        details["new_filename"] = source.filename
    if payload.enabled is None and payload.filename is None:
        raise HTTPException(status_code=400, detail="No turnpoint source changes provided.")
    log_action(session, actor_user_id=admin.id, action="turnpoint.update_source", entity_type="turnpoint_source", entity_id=str(source.id), details=details)
    session.commit()
    session.refresh(source)
    return _source_payload(session, source)


@router.delete("/api/events/{event_id}/turnpoint-sources/{source_id}", status_code=204)
def delete_turnpoint_source(event_id: int, source_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    source = session.get(TurnpointSource, source_id)
    if source is None or source.event_id != event_id:
        raise HTTPException(status_code=404, detail="Turnpoint source not found")

    filename = source.filename
    stored_path = Path(source.stored_path)
    deleted_turnpoint_ids = list(session.scalars(select(Turnpoint.id).where(Turnpoint.source_id == source.id)).all())
    _delete_task_points_for_turnpoints(session, deleted_turnpoint_ids)
    session.query(Turnpoint).filter(Turnpoint.source_id == source.id).delete()
    session.delete(source)
    session.flush()

    if stored_path.exists():
        stored_path.unlink(missing_ok=True)
        if stored_path.parent.exists() and not any(stored_path.parent.iterdir()):
            stored_path.parent.rmdir()

    log_action(session, actor_user_id=admin.id, action="turnpoint.delete", entity_type="turnpoint_source", entity_id=str(source_id), details={"event_id": event_id, "source_id": source_id, "filename": filename})
    session.commit()
