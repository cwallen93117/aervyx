from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import SiteSettings, User
from app.schemas import SiteSettingsResponse, SiteSettingsUpdate

router = APIRouter(prefix="/api/site-settings", tags=["site-settings"])


def _get_site_settings(session: Session) -> SiteSettings:
    settings = session.get(SiteSettings, 1)
    if settings is None:
        settings = SiteSettings(
            id=1,
            telemetry_vario_smoothing_seconds=5,
            telemetry_altitude_smoothing_seconds=3,
            telemetry_speed_smoothing_seconds=3,
            telemetry_glide_ratio_smoothing_seconds=5,
            max_map_pitch_degrees=75,
            site_match_radius_m=1000,
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


@router.get("", response_model=SiteSettingsResponse)
def get_site_settings(_: User = Depends(get_current_user), session: Session = Depends(get_session)) -> SiteSettingsResponse:
    return SiteSettingsResponse.model_validate(_get_site_settings(session))


@router.patch("", response_model=SiteSettingsResponse)
def update_site_settings(
    payload: SiteSettingsUpdate,
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> SiteSettingsResponse:
    settings = _get_site_settings(session)
    settings.telemetry_vario_smoothing_seconds = payload.telemetry_vario_smoothing_seconds
    settings.telemetry_altitude_smoothing_seconds = payload.telemetry_altitude_smoothing_seconds
    settings.telemetry_speed_smoothing_seconds = payload.telemetry_speed_smoothing_seconds
    settings.telemetry_glide_ratio_smoothing_seconds = payload.telemetry_glide_ratio_smoothing_seconds
    settings.max_map_pitch_degrees = payload.max_map_pitch_degrees
    settings.site_match_radius_m = payload.site_match_radius_m
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return SiteSettingsResponse.model_validate(settings)
