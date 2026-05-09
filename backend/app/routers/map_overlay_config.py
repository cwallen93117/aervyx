import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import MapOverlayConfig, User
from app.schemas import MapOverlayConfigResponse, MapOverlayConfigUpdate
from app.services.map_overlay_config import DEFAULT_MAP_OVERLAY_CONFIG, normalize_map_overlay_config

router = APIRouter(prefix="/api/map-overlay-config", tags=["map-overlay-config"])


def _get_config(session: Session) -> MapOverlayConfig:
    record = session.get(MapOverlayConfig, 1)
    if record is None:
        record = MapOverlayConfig(id=1, config=json.dumps(DEFAULT_MAP_OVERLAY_CONFIG))
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


def _normalized_config(session: Session, record: MapOverlayConfig) -> dict:
    try:
        raw_config = json.loads(record.config)
    except (TypeError, json.JSONDecodeError):
        raw_config = {}
    normalized = normalize_map_overlay_config(raw_config)
    if normalized != raw_config:
        record.config = json.dumps(normalized)
        session.add(record)
        session.commit()
        session.refresh(record)
    return normalized


@router.get("", response_model=MapOverlayConfigResponse)
def get_map_overlay_config(_: User = Depends(get_current_user), session: Session = Depends(get_session)) -> MapOverlayConfigResponse:
    record = _get_config(session)
    return MapOverlayConfigResponse(config=_normalized_config(session, record), updated_at=record.updated_at)


@router.get("/public", response_model=MapOverlayConfigResponse)
def get_public_map_overlay_config(session: Session = Depends(get_session)) -> MapOverlayConfigResponse:
    record = _get_config(session)
    full_config = _normalized_config(session, record)
    public_slice = {
        "schema_version": full_config.get("schema_version", 2),
        "groups": {"public_live": full_config.get("groups", {}).get("public_live", {})},
        "public_live": full_config.get("public_live", {}),
    }
    return MapOverlayConfigResponse(config=public_slice, updated_at=record.updated_at)


@router.patch("", response_model=MapOverlayConfigResponse)
def update_map_overlay_config(
    payload: MapOverlayConfigUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MapOverlayConfigResponse:
    record = _get_config(session)
    record.config = json.dumps(normalize_map_overlay_config(payload.config))
    session.add(record)
    session.commit()
    session.refresh(record)
    return MapOverlayConfigResponse(config=_normalized_config(session, record), updated_at=record.updated_at)
