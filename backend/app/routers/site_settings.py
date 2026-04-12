from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import SiteSettings, User
from app.schemas import SiteSettingsResponse, SiteSettingsUpdate

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
