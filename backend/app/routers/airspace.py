from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import AirspaceRegion, AirspaceSource, Event, User
from app.schemas import AirspaceRegionResponse, AirspaceSourceResponse, AirspaceSourceUpdate, AirspaceUploadResponse
from app.services.airspace import _display_category, parse_airspace_upload
from app.services.audit import log_action

router = APIRouter(tags=["airspace"])


def _kind(kind: str) -> str:
    normalized = kind.strip().lower()
    if normalized not in {"airspace", "restricted_field"}:
        raise HTTPException(status_code=400, detail="Airspace kind must be 'airspace' or 'restricted_field'.")
    return normalized


def _kind_or_blank(kind: str | None) -> str:
    normalized = (kind or "").strip().lower()
    if not normalized:
        return ""
    return _kind(normalized)


def _source_payload(session: Session, source: AirspaceSource) -> AirspaceSourceResponse:
    region_count = session.scalar(select(func.count()).select_from(AirspaceRegion).where(AirspaceRegion.source_id == source.id)) or 0
    return AirspaceSourceResponse(
        id=source.id,
        event_id=source.event_id,
        kind=source.kind,
        filename=source.filename,
        file_format=source.file_format,
        sha256=source.sha256,
        enabled=source.enabled,
        uploaded_at=source.uploaded_at,
        region_count=region_count,
    )


@router.get("/api/events/{event_id}/airspace-sources", response_model=list[AirspaceSourceResponse])
def list_airspace_sources(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[AirspaceSourceResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    sources = session.scalars(select(AirspaceSource).where(AirspaceSource.event_id == event_id).order_by(AirspaceSource.uploaded_at.desc())).all()
    return [_source_payload(session, source) for source in sources]


@router.get("/api/events/{event_id}/airspaces", response_model=list[AirspaceRegionResponse])
def list_airspaces(event_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)) -> list[AirspaceRegionResponse]:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    regions = session.scalars(select(AirspaceRegion).where(AirspaceRegion.event_id == event_id).order_by(AirspaceRegion.is_restricted_field.asc(), AirspaceRegion.name.asc())).all()
    return [AirspaceRegionResponse.model_validate(region) for region in regions]


@router.post("/api/events/{event_id}/airspaces/upload", response_model=AirspaceUploadResponse)
async def upload_airspace(
    event_id: int,
    kind: str = Query(""),
    file: UploadFile = File(...),
    admin: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> AirspaceUploadResponse:
    if session.get(Event, event_id) is None:
        raise HTTPException(status_code=404, detail="Event not found")
    stored_kind = _kind_or_blank(kind)
    parse_kind = stored_kind or "airspace"
    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()
    file_format, records = parse_airspace_upload(file.filename or "airspace.txt", content, kind=parse_kind)
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "airspace" / sha256
    upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = upload_dir / (file.filename or f"airspace.{file_format}")
    if not stored_path.exists():
        stored_path.write_bytes(content)
    source = AirspaceSource(
        event_id=event_id,
        kind=stored_kind,
        filename=file.filename or stored_path.name,
        content_type=file.content_type,
        file_format=file_format,
        sha256=sha256,
        stored_path=str(stored_path),
        enabled=True,
    )
    session.add(source)
    session.flush()
    for record in records:
        session.add(
            AirspaceRegion(
                event_id=event_id,
                source_id=source.id,
                name=record.name,
                class_code=record.class_code,
                type_code=record.type_code,
                display_category=record.display_category,
                lower_limit_label=record.lower_limit_label,
                upper_limit_label=record.upper_limit_label,
                lower_limit_m=record.lower_limit_m,
                upper_limit_m=record.upper_limit_m,
                geometry_json=record.geometry_json,
                label_latitude=record.label_latitude,
                label_longitude=record.label_longitude,
                is_restricted_field=record.is_restricted_field,
            )
        )
    log_action(
        session,
        actor_user_id=admin.id,
        action="airspace.upload",
        entity_type="airspace_source",
        entity_id=str(source.id),
        details={"event_id": event_id, "kind": stored_kind, "parse_kind": parse_kind, "filename": source.filename, "sha256": sha256, "count": len(records)},
    )
    session.commit()
    return AirspaceUploadResponse(source_id=source.id, kind=stored_kind, format=file_format, imported_count=len(records), sha256=sha256, filename=source.filename)


@router.patch("/api/events/{event_id}/airspace-sources/{source_id}", response_model=AirspaceSourceResponse)
def update_airspace_source(event_id: int, source_id: int, payload: AirspaceSourceUpdate, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> AirspaceSourceResponse:
    source = session.get(AirspaceSource, source_id)
    if source is None or source.event_id != event_id:
        raise HTTPException(status_code=404, detail="Airspace source not found")
    updated_fields: dict[str, object] = {"filename": source.filename}
    if payload.enabled is not None:
        source.enabled = payload.enabled
        updated_fields["enabled"] = payload.enabled
    if payload.kind is not None:
        next_kind = _kind_or_blank(payload.kind)
        source.kind = next_kind
        parse_kind = next_kind or "airspace"
        regions = session.scalars(select(AirspaceRegion).where(AirspaceRegion.source_id == source.id)).all()
        for region in regions:
            region.is_restricted_field = next_kind == "restricted_field"
            region.display_category = _display_category(
                kind=parse_kind,
                name=region.name,
                class_code=region.class_code,
                type_code=region.type_code,
            )
        updated_fields["kind"] = next_kind
    log_action(
        session,
        actor_user_id=admin.id,
        action="airspace.update",
        entity_type="airspace_source",
        entity_id=str(source_id),
        details={"event_id": event_id, **updated_fields},
    )
    session.commit()
    session.refresh(source)
    return _source_payload(session, source)


@router.delete("/api/events/{event_id}/airspace-sources/{source_id}", status_code=204)
def delete_airspace_source(event_id: int, source_id: int, admin: User = Depends(require_staff), session: Session = Depends(get_session)) -> None:
    source = session.get(AirspaceSource, source_id)
    if source is None or source.event_id != event_id:
        raise HTTPException(status_code=404, detail="Airspace source not found")
    stored_path = Path(source.stored_path)
    filename = source.filename
    kind = source.kind
    session.delete(source)
    session.flush()
    if stored_path.exists():
        stored_path.unlink(missing_ok=True)
        if stored_path.parent.exists() and not any(stored_path.parent.iterdir()):
            stored_path.parent.rmdir()
    log_action(
        session,
        actor_user_id=admin.id,
        action="airspace.delete",
        entity_type="airspace_source",
        entity_id=str(source_id),
        details={"event_id": event_id, "filename": filename, "kind": kind},
    )
    session.commit()
