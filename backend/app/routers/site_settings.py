from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import SiteSettings, User
from app.schemas import SiteSettingsResponse, SiteSettingsUpdate
from app.services.cloudflare_ddns import normalize_cloudflare_ddns_settings, normalize_cloudflare_record_names, run_cloudflare_ddns_check
from app.services.integration_credentials import IntegrationSecretError, encrypt_secret
from app.services.mqtt_config import (
    LOCAL_MOSQUITTO,
    clear_legacy_public_mqtt_values,
    is_known_mqtt_broker_mode,
    normalize_mqtt_broker_mode,
)
from app.services.mosquitto_passwords import write_mosquitto_password_file

router = APIRouter(prefix="/api/site-settings", tags=["site-settings"])


# Curated set of Meshtastic device settings exposed per profile.
# Mirrors the categories in the official Meshtastic Android app
# (Device / Position / LoRa / Power / Bluetooth / Network / Display / Modules).
# Mobile + frontend share this exact key set — keep them in lockstep.
DEFAULT_MESH_PROFILES = {
    "pilot": {
        # Device
        "role": "tracker",
        "rebroadcast_mode": "all",
        "node_info_broadcast_secs": 10800,
        "serial_enabled": True,
        # Position
        "gps_mode": "enabled",
        "gps_update_interval": 10,
        "position_broadcast_secs": 30,
        "smart_position_enabled": True,
        "smart_min_distance": 100,
        "smart_min_interval": 10,
        "position_flags": 1,
        # LoRa — region is device-specific (set by the operator on the mobile
        # Meshtastic settings screen). Never shipped from the backend so a
        # profile push can never silence a radio that's already on a legal
        # frequency.
        "modem_preset": "long_fast",
        "hop_limit": 3,
        "tx_power": 0,
        "tx_enabled": True,
        "sx126x_rx_boosted_gain": True,
        # Power
        "power_saving": False,
        "on_battery_shutdown_after_secs": 0,
        "ls_secs": 300,
        "wait_bluetooth_secs": 60,
        # Bluetooth — keep enabled + fixed-PIN across every profile so a
        # headless device can never lock admins out (random PIN requires a
        # display, no PIN is insecure).
        "bluetooth_enabled": True,
        "bluetooth_mode": "fixed_pin",
        "bluetooth_fixed_pin": 123456,
        # Network (Wi-Fi SSID/PSK are device-specific — set per device on
        # the phone app, never fleet-wide)
        "wifi_enabled": False,
        "eth_enabled": False,
        # Display
        "display_timeout_secs": 30,
        "auto_screen_carousel_secs": 0,
        "wake_on_tap_or_motion": False,
        # Modules
        "telemetry_interval_secs": 86400,
        "device_telemetry_enabled": True,
        "environment_telemetry_enabled": False,
        "neighbor_info_enabled": False,
        "neighbor_info_interval_secs": 14400,
        "store_forward_enabled": False,
        "store_forward_is_server": False,
    },
    "driver": {
        # Device
        "role": "client",
        "rebroadcast_mode": "all",
        "node_info_broadcast_secs": 10800,
        "serial_enabled": True,
        # Position
        "gps_mode": "enabled",
        "gps_update_interval": 30,
        "position_broadcast_secs": 120,
        "smart_position_enabled": True,
        "smart_min_distance": 200,
        "smart_min_interval": 30,
        "position_flags": 1,
        # LoRa — region is device-specific, set on the phone (see pilot
        # profile comment).
        "modem_preset": "long_fast",
        "hop_limit": 3,
        "tx_power": 0,
        "tx_enabled": True,
        "sx126x_rx_boosted_gain": True,
        # Power
        "power_saving": False,
        "on_battery_shutdown_after_secs": 0,
        "ls_secs": 300,
        "wait_bluetooth_secs": 60,
        # Bluetooth
        "bluetooth_enabled": True,
        "bluetooth_mode": "fixed_pin",
        "bluetooth_fixed_pin": 123456,
        # Network (Wi-Fi credentials stay device-specific)
        "wifi_enabled": False,
        "eth_enabled": False,
        # Display
        "display_timeout_secs": 60,
        "auto_screen_carousel_secs": 0,
        "wake_on_tap_or_motion": True,
        # Modules
        "telemetry_interval_secs": 86400,
        "device_telemetry_enabled": True,
        "environment_telemetry_enabled": False,
        "neighbor_info_enabled": False,
        "neighbor_info_interval_secs": 14400,
        "store_forward_enabled": False,
        "store_forward_is_server": False,
    },
    "driver_wifi": {
        # Device
        "role": "client",
        "rebroadcast_mode": "all",
        "node_info_broadcast_secs": 10800,
        "serial_enabled": True,
        # Position
        "gps_mode": "enabled",
        "gps_update_interval": 30,
        "position_broadcast_secs": 60,
        "smart_position_enabled": True,
        "smart_min_distance": 200,
        "smart_min_interval": 30,
        "position_flags": 1,
        # LoRa — region is device-specific, set on the phone (see pilot
        # profile comment).
        "modem_preset": "long_fast",
        "hop_limit": 3,
        "tx_power": 0,
        "tx_enabled": True,
        "sx126x_rx_boosted_gain": True,
        # Power
        "power_saving": False,
        "on_battery_shutdown_after_secs": 0,
        "ls_secs": 300,
        "wait_bluetooth_secs": 60,
        # Bluetooth — stays on so headless devices can't lock admins out.
        # On ESP32 with Wi-Fi enabled the firmware may still disable BT at
        # runtime, but we declare our intent here.
        "bluetooth_enabled": True,
        "bluetooth_mode": "fixed_pin",
        "bluetooth_fixed_pin": 123456,
        # Network (Wi-Fi credentials stay device-specific)
        "wifi_enabled": True,
        "eth_enabled": False,
        # Display
        "display_timeout_secs": 60,
        "auto_screen_carousel_secs": 0,
        "wake_on_tap_or_motion": True,
        # Modules
        "telemetry_interval_secs": 86400,
        "device_telemetry_enabled": True,
        "environment_telemetry_enabled": False,
        "neighbor_info_enabled": False,
        "neighbor_info_interval_secs": 14400,
        "store_forward_enabled": False,
        "store_forward_is_server": False,
    },
    "repeater": {
        # Device
        "role": "router",
        "rebroadcast_mode": "all",
        "node_info_broadcast_secs": 10800,
        "serial_enabled": True,
        # Position
        "gps_mode": "enabled",
        "gps_update_interval": 0,
        "position_broadcast_secs": 300,
        "smart_position_enabled": False,
        "smart_min_distance": 0,
        "smart_min_interval": 0,
        "position_flags": 1,
        # LoRa — region is device-specific, set on the phone (see pilot
        # profile comment).
        "modem_preset": "long_fast",
        "hop_limit": 3,
        "tx_power": 0,
        "tx_enabled": True,
        "sx126x_rx_boosted_gain": True,
        # Power (repeaters are mains-powered — never auto-shutdown)
        "power_saving": False,
        "on_battery_shutdown_after_secs": 0,
        "ls_secs": 300,
        "wait_bluetooth_secs": 60,
        # Bluetooth
        "bluetooth_enabled": True,
        "bluetooth_mode": "fixed_pin",
        "bluetooth_fixed_pin": 123456,
        # Network (Wi-Fi credentials stay device-specific)
        "wifi_enabled": True,
        "eth_enabled": True,
        # Display (off by default — headless repeater)
        "display_timeout_secs": 0,
        "auto_screen_carousel_secs": 0,
        "wake_on_tap_or_motion": False,
        # Modules — repeaters carry the network's neighbor + store-forward state
        "telemetry_interval_secs": 86400,
        "device_telemetry_enabled": True,
        "environment_telemetry_enabled": False,
        "neighbor_info_enabled": False,
        "neighbor_info_interval_secs": 14400,
        "store_forward_enabled": True,
        "store_forward_is_server": True,
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
            live_position_pruning_enabled=True,
            mqtt_enabled=True,
            mqtt_broker_mode=LOCAL_MOSQUITTO,
            mqtt_port=1883,
            mqtt_tls_enabled=False,
            mqtt_topic_prefix="msh",
            cloudflare_ddns_record_names=normalize_cloudflare_record_names(None),
            cloudflare_ddns_check_interval_hours=12,
            mesh_profiles=DEFAULT_MESH_PROFILES,
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    else:
        broker_mode = normalize_mqtt_broker_mode(settings.mqtt_broker_mode)
        changed = settings.mqtt_broker_mode != broker_mode
        settings.mqtt_broker_mode = broker_mode
        changed = clear_legacy_public_mqtt_values(settings) or changed
        changed = normalize_cloudflare_ddns_settings(settings) or changed
        if changed:
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
    if not is_known_mqtt_broker_mode(payload.mqtt_broker_mode):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported MQTT broker mode.")

    broker_mode = normalize_mqtt_broker_mode(payload.mqtt_broker_mode)
    cloudflare_record_names = normalize_cloudflare_record_names(payload.cloudflare_ddns_record_names)
    if payload.mqtt_enabled:
        if not payload.mqtt_host:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MQTT requires an MQTT host.",
            )
        if payload.mqtt_port < 1 or payload.mqtt_port > 65535:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="MQTT port must be between 1 and 65535.")
        if not payload.mqtt_username or not payload.mqtt_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MQTT requires an MQTT username and password.",
            )

        password_file = get_settings().mosquitto_password_file
        if broker_mode == LOCAL_MOSQUITTO and password_file:
            try:
                write_mosquitto_password_file(
                    password_file,
                    payload.mqtt_username,
                    payload.mqtt_password,
                )
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Could not update Mosquitto password file: {exc}",
                ) from exc
            except ValueError as exc:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    settings = _get_site_settings(session)
    encrypted_cloudflare_token = settings.cloudflare_ddns_encrypted_api_token
    token_value = (payload.cloudflare_ddns_api_token or "").strip()
    if payload.cloudflare_ddns_clear_api_token:
        encrypted_cloudflare_token = None
    elif token_value:
        try:
            encrypted_cloudflare_token = encrypt_secret(token_value)
        except IntegrationSecretError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if payload.cloudflare_ddns_enabled:
        if not (payload.cloudflare_ddns_zone_id or "").strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cloudflare DDNS requires a zone ID.")
        if not encrypted_cloudflare_token:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cloudflare DDNS requires an API token.")
        if not cloudflare_record_names:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cloudflare DDNS requires at least one DNS record.")

    settings.telemetry_vario_smoothing_seconds = payload.telemetry_vario_smoothing_seconds
    settings.telemetry_altitude_smoothing_seconds = payload.telemetry_altitude_smoothing_seconds
    settings.telemetry_speed_smoothing_seconds = payload.telemetry_speed_smoothing_seconds
    settings.telemetry_glide_ratio_smoothing_seconds = payload.telemetry_glide_ratio_smoothing_seconds
    settings.max_map_pitch_degrees = payload.max_map_pitch_degrees
    settings.site_match_radius_m = payload.site_match_radius_m
    settings.live_position_pruning_enabled = payload.live_position_pruning_enabled
    settings.mqtt_enabled = payload.mqtt_enabled
    settings.mqtt_broker_mode = broker_mode
    settings.mqtt_host = payload.mqtt_host
    settings.mqtt_port = payload.mqtt_port
    settings.mqtt_tls_enabled = payload.mqtt_tls_enabled
    settings.mqtt_username = payload.mqtt_username
    settings.mqtt_password = payload.mqtt_password
    settings.mqtt_topic_prefix = payload.mqtt_topic_prefix
    settings.mqtt_channel_psk = payload.mqtt_channel_psk
    settings.cloudflare_ddns_enabled = payload.cloudflare_ddns_enabled
    settings.cloudflare_ddns_zone_id = (payload.cloudflare_ddns_zone_id or "").strip() or None
    settings.cloudflare_ddns_encrypted_api_token = encrypted_cloudflare_token
    settings.cloudflare_ddns_record_names = cloudflare_record_names
    settings.cloudflare_ddns_check_interval_hours = payload.cloudflare_ddns_check_interval_hours
    if payload.mesh_profiles is not None:
        settings.mesh_profiles = payload.mesh_profiles
    session.add(settings)
    session.commit()
    session.refresh(settings)

    # Signal MQTT subscriber to reconnect with new settings
    from app.services.mqtt_subscriber import request_mqtt_reconnect
    request_mqtt_reconnect()

    return SiteSettingsResponse.model_validate(settings)


@router.post("/cloudflare-ddns/check", response_model=SiteSettingsResponse)
async def check_cloudflare_ddns(
    _: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> SiteSettingsResponse:
    settings = await run_cloudflare_ddns_check(session)
    return SiteSettingsResponse.model_validate(settings)
