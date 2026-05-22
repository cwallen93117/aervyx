from __future__ import annotations

LOCAL_MOSQUITTO = "local_mosquitto"
CLOUD_VM = "cloud_vm"
LEGACY_PRIVATE = "private"
LEGACY_PUBLIC = "public"
LEGACY_PUBLIC_HOST = "mqtt.meshtastic.org"
LEGACY_PUBLIC_USERNAME = "meshdev"
LEGACY_PUBLIC_PASSWORD = "large4cats"

KNOWN_MQTT_BROKER_MODES = {
    LOCAL_MOSQUITTO,
    CLOUD_VM,
    LEGACY_PRIVATE,
    LEGACY_PUBLIC,
}


def normalize_mqtt_broker_mode(value: str | None) -> str:
    if value in {CLOUD_VM, LEGACY_PRIVATE}:
        return CLOUD_VM
    return LOCAL_MOSQUITTO


def is_known_mqtt_broker_mode(value: str | None) -> bool:
    return value in KNOWN_MQTT_BROKER_MODES or value in {None, ""}


def clear_legacy_public_mqtt_values(settings: object) -> bool:
    """Remove old public Meshtastic broker defaults from a settings object."""
    changed = False
    if getattr(settings, "mqtt_host", None) == LEGACY_PUBLIC_HOST:
        setattr(settings, "mqtt_host", None)
        changed = True
    if getattr(settings, "mqtt_username", None) == LEGACY_PUBLIC_USERNAME:
        setattr(settings, "mqtt_username", None)
        changed = True
    if getattr(settings, "mqtt_password", None) == LEGACY_PUBLIC_PASSWORD:
        setattr(settings, "mqtt_password", None)
        changed = True
    return changed
