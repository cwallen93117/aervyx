from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import SiteSettings, User
from app.schemas import SiteSettingsResponse, SiteSettingsUpdate

router = APIRouter(prefix="/api/site-settings", tags=["site-settings"])


DEFAULT_MESH_PROFILES = {
    "pilot": {
        "role": "tracker", "rebroadcast_mode": "all", "gps_mode": "enabled",
        "position_broadcast_secs": 30, "smart_position_enabled": True,
        "smart_min_distance": 100, "smart_min_interval": 30,
        "modem_preset": "long_fast", "hop_limit": 3, "power_saving": False,
        "bluetooth_enabled": True, "wifi_enabled": False,
        "position_flags": 1, "display_timeout_secs": 30, "telemetry_interval_secs": 86400,
    },
    "driver": {
        "role": "client", "rebroadcast_mode": "all", "gps_mode": "enabled",
        "position_broadcast_secs": 120, "smart_position_enabled": True,
        "smart_min_distance": 200, "smart_min_interval": 60,
        "modem_preset": "long_fast", "hop_limit": 3, "power_saving": False,
        "bluetooth_enabled": True, "wifi_enabled": False,
        "position_flags": 1, "display_timeout_secs": 60, "telemetry_interval_secs": 86400,
    },
    "driver_wifi": {
        "role": "client", "rebroadcast_mode": "all", "gps_mode": "enabled",
        "position_broadcast_secs": 60, "smart_position_enabled": True,
        "smart_min_distance": 200, "smart_min_interval": 30,
        "modem_preset": "long_fast", "hop_limit": 3, "power_saving": False,
        "bluetooth_enabled": True, "wifi_enabled": True,
        "position_flags": 1, "display_timeout_secs": 60, "telemetry_interval_secs": 86400,
    },
    "repeater": {
        "role": "router", "rebroadcast_mode": "all", "gps_mode": "enabled",
        "position_broadcast_secs": 300, "smart_position_enabled": False,
        "smart_min_distance": 0, "smart_min_interval": 0,
        "modem_preset": "long_fast", "hop_limit": 3, "power_saving": False,
        "bluetooth_enabled": True, "wifi_enabled": True,
        "position_flags": 1, "display_timeout_secs": 0, "telemetry_interval_secs": 86400,
    },
}


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
            mqtt_enabled=True,
            mqtt_broker_mode="public",
            mqtt_port=1883,
            mqtt_topic_prefix="msh",
            mesh_profiles=DEFAULT_MESH_PROFILES,
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
    settings.mqtt_enabled = payload.mqtt_enabled
    settings.mqtt_broker_mode = payload.mqtt_broker_mode
    settings.mqtt_host = payload.mqtt_host
    settings.mqtt_port = payload.mqtt_port
    settings.mqtt_topic_prefix = payload.mqtt_topic_prefix
    settings.mqtt_channel_psk = payload.mqtt_channel_psk
    if payload.mesh_profiles is not None:
        settings.mesh_profiles = payload.mesh_profiles
    session.add(settings)
    session.commit()
    session.refresh(settings)

    # Signal MQTT subscriber to reconnect with new settings
    from app.services.mqtt_subscriber import mqtt_reconnect_event
    if mqtt_reconnect_event is not None:
        mqtt_reconnect_event.set()

    return SiteSettingsResponse.model_validate(settings)
