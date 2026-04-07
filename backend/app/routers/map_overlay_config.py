import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.db.schema import DEFAULT_MAP_OVERLAY_CONFIG
from app.deps import get_current_user, require_admin
from app.models import MapOverlayConfig, User
from app.schemas import MapOverlayConfigResponse, MapOverlayConfigUpdate

router = APIRouter(prefix="/api/map-overlay-config", tags=["map-overlay-config"])


def _get_config(session: Session) -> MapOverlayConfig:
    record = session.get(MapOverlayConfig, 1)
    if record is None:
        record = MapOverlayConfig(id=1, config=json.dumps(DEFAULT_MAP_OVERLAY_CONFIG))
        session.add(record)
        session.commit()
        session.refresh(record)
    return record


@router.get("", response_model=MapOverlayConfigResponse)
def get_map_overlay_config(_: User = Depends(get_current_user), session: Session = Depends(get_session)) -> MapOverlayConfigResponse:
    record = _get_config(session)
    return MapOverlayConfigResponse(config=json.loads(record.config), updated_at=record.updated_at)


@router.patch("", response_model=MapOverlayConfigResponse)
def update_map_overlay_config(
    payload: MapOverlayConfigUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> MapOverlayConfigResponse:
    record = _get_config(session)
    record.config = json.dumps(payload.config)
    session.add(record)
    session.commit()
    session.refresh(record)
    return MapOverlayConfigResponse(config=json.loads(record.config), updated_at=record.updated_at)
