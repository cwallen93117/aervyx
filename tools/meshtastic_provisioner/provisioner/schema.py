"""Editable profile matrix schema shown in the desktop provisioner."""

from __future__ import annotations

from dataclasses import dataclass


PROFILE_KEYS = ("pilot", "driver", "driver_wifi", "base_station", "wired_base_station")
PROFILE_LABELS = {
    "pilot": "Pilot",
    "driver": "Driver",
    "driver_wifi": "Driver Wi-Fi",
    "base_station": "Base Station",
    "wired_base_station": "Wired Base Station",
}


@dataclass(frozen=True)
class MatrixRow:
    group: str
    label: str
    path: str
    kind: str = "string"
    secret: bool = False
    description: str = ""
    options: tuple[str, ...] = ()


POSITION_FLAGS: tuple[tuple[int, str], ...] = (
    (0x01, "Altitude"),
    (0x02, "Altitude MSL"),
    (0x04, "Geoidal separation"),
    (0x08, "DOP"),
    (0x10, "HDOP/VDOP"),
    (0x20, "Satellites in view"),
    (0x40, "Sequence number"),
    (0x80, "Timestamp"),
    (0x100, "Heading"),
    (0x200, "Speed"),
)


ROLE_OPTIONS = ("TRACKER", "ROUTER", "CLIENT")
REBROADCAST_OPTIONS = ("ALL", "ALL_SKIP_DECODING", "LOCAL_ONLY", "KNOWN_ONLY", "NONE", "CORE_PORTNUMS_ONLY")
GPS_MODE_OPTIONS = ("DISABLED", "ENABLED", "NOT_PRESENT")
REGION_OPTIONS = ("UNSET", "US", "EU_433", "EU_868", "CN", "JP", "ANZ", "KR", "TW", "RU", "IN", "NZ_865", "TH", "LORA_24", "UA_433", "UA_868")
MODEM_PRESET_OPTIONS = ("LONG_FAST", "LONG_MODERATE", "LONG_SLOW", "VERY_LONG_SLOW", "MEDIUM_SLOW", "MEDIUM_FAST", "SHORT_SLOW", "SHORT_FAST", "SHORT_TURBO", "LONG_TURBO")
BLUETOOTH_MODE_OPTIONS = ("RANDOM_PIN", "FIXED_PIN", "NO_PIN")


MATRIX_ROWS: tuple[MatrixRow, ...] = (
    MatrixRow("Device", "Role", "config.device.role", options=ROLE_OPTIONS),
    MatrixRow("Device", "Rebroadcast", "config.device.rebroadcast_mode", options=REBROADCAST_OPTIONS),
    MatrixRow("Device", "Serial API", "config.device.serial_enabled", "boolean"),
    MatrixRow("Device", "Node info (s)", "config.device.node_info_broadcast_secs", "number"),
    MatrixRow("Position", "GPS mode", "config.position.gps_mode", options=GPS_MODE_OPTIONS),
    MatrixRow("Position", "GPS poll (s)", "config.position.gps_update_interval", "number"),
    MatrixRow("Position", "Broadcast (s)", "config.position.position_broadcast_secs", "number"),
    MatrixRow("Position", "Smart position", "config.position.position_broadcast_smart_enabled", "boolean"),
    MatrixRow("Position", "Smart min distance (m)", "config.position.broadcast_smart_minimum_distance", "number"),
    MatrixRow("Position", "Smart min interval (s)", "config.position.broadcast_smart_minimum_interval_secs", "number"),
    MatrixRow("Position", "Position flags", "config.position.position_flags", "flags"),
    MatrixRow("LoRa", "Region", "config.lora.region", options=REGION_OPTIONS),
    MatrixRow("LoRa", "Use preset", "config.lora.use_preset", "boolean"),
    MatrixRow("LoRa", "Modem preset", "config.lora.modem_preset", options=MODEM_PRESET_OPTIONS),
    MatrixRow("LoRa", "Hop limit", "config.lora.hop_limit", "number"),
    MatrixRow("LoRa", "TX power", "config.lora.tx_power", "number"),
    MatrixRow("LoRa", "TX enabled", "config.lora.tx_enabled", "boolean"),
    MatrixRow("LoRa", "RX boosted gain", "config.lora.sx126x_rx_boosted_gain", "boolean"),
    MatrixRow("Power", "Power saving", "config.power.is_power_saving", "boolean"),
    MatrixRow("Power", "Battery shutdown (s)", "config.power.on_battery_shutdown_after_secs", "number"),
    MatrixRow("Power", "Light sleep (s)", "config.power.ls_secs", "number"),
    MatrixRow("Power", "Bluetooth wait (s)", "config.power.wait_bluetooth_secs", "number"),
    MatrixRow("Bluetooth", "Bluetooth", "config.bluetooth.enabled", "boolean"),
    MatrixRow("Bluetooth", "Pairing mode", "config.bluetooth.mode", options=BLUETOOTH_MODE_OPTIONS),
    MatrixRow("Bluetooth", "Fixed PIN", "config.bluetooth.fixed_pin", "number", True),
    MatrixRow("Network", "Wi-Fi", "config.network.wifi_enabled", "boolean"),
    MatrixRow("Network", "Wi-Fi SSID", "config.network.wifi_ssid"),
    MatrixRow("Network", "Wi-Fi password", "config.network.wifi_psk", "string", True),
    MatrixRow("Network", "Ethernet", "config.network.eth_enabled", "boolean"),
    MatrixRow("Display", "Display timeout (s)", "config.display.screen_on_secs", "number"),
    MatrixRow("Display", "Carousel (s)", "config.display.auto_screen_carousel_secs", "number"),
    MatrixRow("Display", "Wake on tap/motion", "config.display.wake_on_tap_or_motion", "boolean"),
    MatrixRow("MQTT", "MQTT enabled", "module_config.mqtt.enabled", "boolean"),
    MatrixRow("MQTT", "Broker address", "module_config.mqtt.address"),
    MatrixRow("MQTT", "Username", "module_config.mqtt.username"),
    MatrixRow("MQTT", "Password", "module_config.mqtt.password", "string", True),
    MatrixRow("MQTT", "Encryption enabled", "module_config.mqtt.encryption_enabled", "boolean"),
    MatrixRow("MQTT", "TLS enabled", "module_config.mqtt.tls_enabled", "boolean"),
    MatrixRow("MQTT", "Topic root", "module_config.mqtt.root"),
    MatrixRow("MQTT", "Proxy to client", "module_config.mqtt.proxy_to_client_enabled", "boolean"),
    MatrixRow("MQTT", "Map reporting", "module_config.mqtt.map_reporting_enabled", "boolean"),
    MatrixRow("MQTT", "Map report interval (s)", "module_config.mqtt.map_report_settings.publish_interval_secs", "number"),
    MatrixRow("MQTT", "Map precision", "module_config.mqtt.map_report_settings.position_precision", "number"),
    MatrixRow("MQTT", "Report location", "module_config.mqtt.map_report_settings.should_report_location", "boolean"),
    MatrixRow("Telemetry", "Telemetry interval (s)", "module_config.telemetry.device_update_interval", "number"),
    MatrixRow("Telemetry", "Device telemetry", "module_config.telemetry.device_telemetry_enabled", "boolean"),
    MatrixRow("Telemetry", "Environment telemetry", "module_config.telemetry.environment_measurement_enabled", "boolean"),
    MatrixRow("Neighbor Info", "Neighbor info", "module_config.neighbor_info.enabled", "boolean"),
    MatrixRow("Neighbor Info", "Neighbor interval (s)", "module_config.neighbor_info.update_interval", "number"),
    MatrixRow("Store & Forward", "Store & forward", "module_config.store_forward.enabled", "boolean"),
    MatrixRow("Store & Forward", "S&F server", "module_config.store_forward.is_server", "boolean"),
    MatrixRow("Primary Channel", "Channel name", "channel.primary.name"),
    MatrixRow("Primary Channel", "Primary PSK", "channel.primary.psk", "string", True),
    MatrixRow("Primary Channel", "Uplink enabled", "channel.primary.uplink_enabled", "boolean"),
    MatrixRow("Primary Channel", "Downlink enabled", "channel.primary.downlink_enabled", "boolean"),
)


def get_path(data: dict, path: str, default=None):
    current = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_path(data: dict, path: str, value) -> None:
    current = data
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def format_position_flags(value: int) -> str:
    selected = [label for bit, label in POSITION_FLAGS if value & bit]
    return ", ".join(selected) if selected else "None"
