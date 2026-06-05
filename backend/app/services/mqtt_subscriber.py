"""Background MQTT subscriber for Meshtastic position messages.

Connects to the configured MQTT broker (read from site_settings DB),
subscribes to ``<prefix>/#`` and persists incoming position reports for
registered platform devices into the ``live_positions`` table with
``source='mqtt_gateway'``.

Supports two payload formats:

1. **JSON** (custom Aervyx payloads)::

    {
        "latitude": <float>,
        "longitude": <float>,
        "altitude": <float>,        # optional
        "speed": <float>,           # optional, ground speed
        "heading": <float>,         # optional, degrees
        "device_id": "<string>",    # Meshtastic node id
        "task_id": <int>,           # competition task id
        "pilot_id": <int>,          # optional
        "battery_level": <int>,     # optional, 0-100
        "timestamp": "<iso8601>"    # optional, defaults to now
    }

2. **Protobuf** (native Meshtastic ServiceEnvelope messages published by
   real devices).  These are decoded with a lightweight hand-parser -- no
   protobuf library required.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import struct
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import paho.mqtt.client as paho_mqtt
from sqlalchemy import select

from app.core.config import get_settings
from app.db import SessionLocal
from app.models import MeshNodeStatus, SiteSettings, User
from app.services.mesh_ids import normalize_mesh_device_id
from app.services.mqtt_config import LOCAL_MOSQUITTO, clear_legacy_public_mqtt_values, normalize_mqtt_broker_mode
from app.services.tracking import (
    mesh_purpose_to_profile_type,
    plausible_live_altitude_or_none,
    prune_old_live_positions,
    resolve_active_task_id,
    resolve_active_task_id_for_user,
    resolve_mesh_device_assignment,
    store_position,
)

logger = logging.getLogger("aervyx.mqtt")

# Module-level state exposed for the admin debug endpoint
mqtt_connected: bool = False
mqtt_last_message_at: datetime | None = None

# Event set by settings/device handlers to trigger reconnection
mqtt_reconnect_event: threading.Event | None = None

# In-memory battery cache: device_id → (battery_level, timestamp)
# Populated from TELEMETRY_APP (portnum 67) messages and injected into
# subsequent POSITION_APP messages for the same device.
_battery_cache: dict[str, tuple[int, float]] = {}
_BATTERY_CACHE_MAX_AGE_S = 3600  # Ignore cached battery older than 1 hour
_MESHTASTIC_DEFAULT_PSK = bytes.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")

PORTNUM_PACKET_TYPES = {
    3: "POSITION_APP",
    4: "NODEINFO_APP",
    5: "ROUTING_APP",
    67: "TELEMETRY_APP",
    71: "NEIGHBORINFO_APP",
    73: "MAP_REPORT_APP",
}


@dataclass
class DecodedMeshEnvelope:
    from_node: int | None
    portnum: int | None
    payload_bytes: bytes | None
    gateway_id: str | None = None
    channel_id: str | None = None
    encrypted: bool = False
    decrypted: bool = False


def _normalize_mesh_node_id(value: str | None) -> str | None:
    candidate = (value or "").strip().lower()
    if not candidate:
        return None
    if candidate.startswith("!"):
        return candidate
    if len(candidate) == 8 and all(ch in "0123456789abcdef" for ch in candidate):
        return f"!{candidate}"
    return candidate


def _format_node_id(node_num: int | None) -> str | None:
    return f"!{node_num:08x}" if node_num is not None else None


def _packet_type_for_portnum(portnum: int | None) -> str:
    if portnum is None:
        return "UNKNOWN_APP"
    return PORTNUM_PACKET_TYPES.get(portnum, f"unknown_{portnum}")


def _decode_string(raw: bytes | None) -> str | None:
    if not raw:
        return None
    try:
        return raw.decode("utf-8", errors="ignore").strip() or None
    except Exception:
        return None


def _gateway_id_from_topic(topic: str | None) -> str | None:
    if not topic:
        return None
    candidate = topic.strip().split("/")[-1]
    return _normalize_mesh_node_id(candidate)


def _parse_position(raw: bytes | bytearray) -> dict | None:
    """Try to parse a JSON position payload. Returns None on failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Ignoring non-JSON MQTT message")
        return None

    if not isinstance(data, dict):
        return None

    # Require at minimum lat and lon (task_id is resolved later if missing)
    lat = data.get("latitude")
    lon = data.get("longitude")
    task_id = data.get("task_id")
    if lat is None or lon is None:
        logger.debug("Ignoring MQTT message missing latitude or longitude")
        return None

    ts_raw = data.get("timestamp")
    ts = None
    if ts_raw:
        try:
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            pass

    return {
        "task_id": int(task_id) if task_id is not None else None,
        "lat": float(lat),
        "lon": float(lon),
        "alt": float(data["altitude"]) if data.get("altitude") is not None else None,
        "speed": float(data["speed"]) if data.get("speed") is not None else None,
        "heading": float(data["heading"]) if data.get("heading") is not None else None,
        "accuracy": float(data["accuracy"]) if data.get("accuracy") is not None else None,
        "timestamp": ts,
        "source": "mqtt_gateway",
        "device_id": str(data["device_id"]) if data.get("device_id") is not None else None,
        "mesh_seq_number": int(data["mesh_seq_number"]) if data.get("mesh_seq_number") is not None else None,
        "battery_level": int(data["battery_level"]) if data.get("battery_level") is not None else None,
        "pilot_id": int(data["pilot_id"]) if data.get("pilot_id") is not None else None,
    }


# ---------------------------------------------------------------------------
# Lightweight protobuf wire-format helpers
# ---------------------------------------------------------------------------
# Protobuf wire types:
#   0 = varint, 1 = 64-bit, 2 = length-delimited, 5 = 32-bit (fixed32/sfixed32)

def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    """Read a varint from *data* starting at *offset*.

    Returns ``(value, new_offset)``.  Raises ``ValueError`` on truncation.
    """
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, offset
        shift += 7
    raise ValueError("Truncated varint")


def _decode_zigzag(n: int) -> int:
    """Decode a ZigZag-encoded signed integer (sint32/sint64)."""
    return (n >> 1) ^ -(n & 1)


def _parse_protobuf_fields(data: bytes) -> dict[int, list[tuple[int, bytes | int]]]:
    """Parse raw protobuf bytes into ``{field_number: [(wire_type, value), ...]}``.

    For wire type 0 (varint), *value* is an ``int``.
    For wire type 2 (length-delimited), *value* is ``bytes``.
    For wire type 5 (32-bit), *value* is raw 4 ``bytes``.
    Wire types 1 (64-bit) are consumed but not stored.
    """
    fields: dict[int, list[tuple[int, bytes | int]]] = {}
    offset = 0
    while offset < len(data):
        tag, offset = _read_varint(data, offset)
        wire_type = tag & 0x07
        field_number = tag >> 3

        if wire_type == 0:  # varint
            value, offset = _read_varint(data, offset)
            fields.setdefault(field_number, []).append((wire_type, value))
        elif wire_type == 1:  # 64-bit fixed
            offset += 8  # skip
        elif wire_type == 2:  # length-delimited
            length, offset = _read_varint(data, offset)
            value = data[offset : offset + length]
            offset += length
            fields.setdefault(field_number, []).append((wire_type, value))
        elif wire_type == 5:  # 32-bit fixed
            value = data[offset : offset + 4]
            offset += 4
            fields.setdefault(field_number, []).append((wire_type, value))
        else:
            # Unknown wire type -- bail out rather than misparse
            break

    return fields


def _get_varint(fields: dict, field_number: int) -> int | None:
    """Return the first varint value for *field_number*, or ``None``."""
    entries = fields.get(field_number)
    if not entries:
        return None
    wt, val = entries[0]
    return val if wt == 0 else None


def _get_bytes(fields: dict, field_number: int) -> bytes | None:
    """Return the first length-delimited value for *field_number*, or ``None``."""
    entries = fields.get(field_number)
    if not entries:
        return None
    wt, val = entries[0]
    return val if wt == 2 else None


def _get_fixed32(fields: dict, field_number: int) -> int | None:
    """Return the first fixed32 (unsigned) value for *field_number*, or ``None``."""
    entries = fields.get(field_number)
    if not entries:
        return None
    wt, val = entries[0]
    if wt == 5 and isinstance(val, (bytes, bytearray)) and len(val) == 4:
        return struct.unpack("<I", val)[0]
    return None


def _get_uint32(fields: dict, field_number: int) -> int | None:
    """Return the first uint32/fixed32 value for *field_number*, or ``None``."""
    value = _get_varint(fields, field_number)
    if value is not None:
        return value
    return _get_fixed32(fields, field_number)


def _decode_int32_varint(value: int) -> int:
    """Decode a protobuf int32 varint, including sign-extended negative values."""
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _get_int32(fields: dict, field_number: int) -> int | None:
    """Return the first int32 varint/sfixed32 value for *field_number*, or ``None``."""
    value = _get_varint(fields, field_number)
    if value is not None:
        return _decode_int32_varint(value)
    return _get_sfixed32(fields, field_number)


def _get_sint32(fields: dict, field_number: int) -> int | None:
    """Return the first zigzag-encoded sint32 value for *field_number*, or ``None``."""
    value = _get_varint(fields, field_number)
    if value is None:
        return None
    return (value >> 1) ^ -(value & 1)


def _get_sfixed32(fields: dict, field_number: int) -> int | None:
    """Return the first sfixed32 (signed) value for *field_number*, or ``None``."""
    entries = fields.get(field_number)
    if not entries:
        return None
    wt, val = entries[0]
    if wt == 5 and isinstance(val, (bytes, bytearray)) and len(val) == 4:
        return struct.unpack("<i", val)[0]
    return None


def _expanded_meshtastic_psk(raw: bytes) -> bytes | None:
    """Expand Meshtastic channel PSK aliases to AES key bytes."""
    if len(raw) == 0:
        return b""
    if len(raw) == 1:
        psk_index = raw[0]
        if psk_index == 0:
            return b""
        key = bytearray(_MESHTASTIC_DEFAULT_PSK)
        key[-1] = (key[-1] + psk_index - 1) & 0xFF
        return bytes(key)
    if len(raw) in (16, 32):
        return raw
    if len(raw) < 16:
        return raw.ljust(16, b"\x00")
    if len(raw) < 32:
        return raw.ljust(32, b"\x00")
    return None


def _decode_psk_text(value: str | None) -> bytes | None:
    candidate = (value or "").strip()
    if not candidate:
        return _expanded_meshtastic_psk(b"\x01")

    hex_candidate = candidate.replace(" ", "").replace(":", "").replace("-", "")
    if len(hex_candidate) % 2 == 0 and all(ch in "0123456789abcdefABCDEF" for ch in hex_candidate):
        try:
            return _expanded_meshtastic_psk(bytes.fromhex(hex_candidate))
        except ValueError:
            pass

    try:
        return _expanded_meshtastic_psk(base64.b64decode(candidate, validate=True))
    except (ValueError, binascii.Error):
        logger.warning("Ignoring invalid Meshtastic MQTT channel PSK setting")
        return None


def _mqtt_channel_psk_candidates(setting_value: str | None) -> list[bytes]:
    """Return candidate channel PSKs, trying configured and default keys."""
    candidates: list[bytes] = []
    configured = _decode_psk_text(setting_value)
    default_key = _expanded_meshtastic_psk(b"\x01")
    for key in (configured, default_key):
        if key is not None and key not in candidates:
            candidates.append(key)
    return candidates


def _read_mqtt_channel_psks_from_db() -> list[bytes]:
    session = SessionLocal()
    try:
        site = session.get(SiteSettings, 1)
        return _mqtt_channel_psk_candidates(site.mqtt_channel_psk if site else None)
    finally:
        session.close()


def _decrypt_meshtastic_payload(
    encrypted_bytes: bytes,
    *,
    from_node: int | None,
    packet_id: int | None,
    psk: bytes,
) -> bytes | None:
    if from_node is None or not psk or len(psk) not in (16, 32):
        return None
    nonce = struct.pack("<Q", packet_id or 0) + struct.pack("<I", from_node) + b"\x00" * 4
    try:
        decryptor = Cipher(algorithms.AES(psk), modes.CTR(nonce)).decryptor()
        return decryptor.update(encrypted_bytes) + decryptor.finalize()
    except ValueError as exc:
        logger.debug("Failed to decrypt Meshtastic payload: %s", exc)
        return None


def _decode_data_message(data_bytes: bytes, *, require_known_portnum: bool = False) -> tuple[int | None, bytes | None] | None:
    data_fields = _parse_protobuf_fields(data_bytes)
    portnum = _get_varint(data_fields, 1)
    payload_bytes = _get_bytes(data_fields, 2)
    if require_known_portnum and portnum not in PORTNUM_PACKET_TYPES:
        return None
    return portnum, payload_bytes


def _decode_mesh_envelope(raw: bytes, channel_psks: list[bytes] | None = None) -> DecodedMeshEnvelope | None:
    """Decode a Meshtastic ServiceEnvelope → MeshPacket → Data.

    Returns a decoded envelope or ``None`` on failure.
    """
    try:
        envelope_fields = _parse_protobuf_fields(raw)
        mesh_packet_bytes = _get_bytes(envelope_fields, 1)
        if mesh_packet_bytes is None:
            return None
        channel_id = _decode_string(_get_bytes(envelope_fields, 2))
        gateway_id = _normalize_mesh_node_id(_decode_string(_get_bytes(envelope_fields, 3)))

        mp_fields = _parse_protobuf_fields(mesh_packet_bytes)
        from_node = _get_fixed32(mp_fields, 1)
        packet_id = _get_fixed32(mp_fields, 6)

        data_bytes = _get_bytes(mp_fields, 4)
        if data_bytes is None:
            # Legacy/internal Aervyx packets used field 3 before this parser
            # matched the official MeshPacket oneof. Field 3 is normally channel.
            data_bytes = _get_bytes(mp_fields, 3)

        if data_bytes is not None:
            decoded_data = _decode_data_message(data_bytes)
            if decoded_data is None:
                return None
            portnum, payload_bytes = decoded_data
            return DecodedMeshEnvelope(
                from_node=from_node,
                portnum=portnum,
                payload_bytes=payload_bytes,
                gateway_id=gateway_id,
                channel_id=channel_id,
            )

        encrypted_bytes = _get_bytes(mp_fields, 5)
        if encrypted_bytes is None:
            logger.debug("Protobuf MeshPacket has no decoded or encrypted Data")
            return None

        for psk in channel_psks or []:
            decrypted_bytes = _decrypt_meshtastic_payload(
                encrypted_bytes,
                from_node=from_node,
                packet_id=packet_id,
                psk=psk,
            )
            if decrypted_bytes is None:
                continue
            try:
                decoded_data = _decode_data_message(decrypted_bytes, require_known_portnum=True)
            except (ValueError, struct.error, IndexError, KeyError):
                continue
            if decoded_data is None:
                continue
            portnum, payload_bytes = decoded_data
            return DecodedMeshEnvelope(
                from_node=from_node,
                portnum=portnum,
                payload_bytes=payload_bytes,
                gateway_id=gateway_id,
                channel_id=channel_id,
                encrypted=True,
                decrypted=True,
            )

        return DecodedMeshEnvelope(
            from_node=from_node,
            portnum=None,
            payload_bytes=None,
            gateway_id=gateway_id,
            channel_id=channel_id,
            encrypted=True,
            decrypted=False,
        )
    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode protobuf ServiceEnvelope: %s", exc)
        return None


def _parse_protobuf_telemetry(raw: bytes, from_node: int | None) -> int | None:
    """Decode a TELEMETRY_APP payload and cache battery level by device_id.

    Meshtastic Telemetry message layout:
      field 1 = time (uint32, unix timestamp)
      field 2 = device_metrics (DeviceMetrics, length-delimited)

    DeviceMetrics layout:
      field 1 = battery_level (uint32, 0-100)
      field 2 = voltage (float)
      field 3 = channel_utilization (float)
      field 4 = air_util_tx (float)
      field 5 = uptime_seconds (uint32)
    """
    device_id = f"!{from_node:08x}" if from_node is not None else None
    if not device_id:
        return None

    try:
        telemetry_fields = _parse_protobuf_fields(raw)

        # Field 2 = device_metrics (length-delimited)
        metrics_bytes = _get_bytes(telemetry_fields, 2)
        if metrics_bytes is None:
            # Could be environment_metrics or power_metrics — not device_metrics
            return None

        metrics_fields = _parse_protobuf_fields(metrics_bytes)

        # Field 1 = battery_level (uint32)
        battery = _get_varint(metrics_fields, 1)
        if battery is not None and 0 <= battery <= 100:
            _battery_cache[device_id] = (battery, time.time())
            logger.debug("Cached battery for %s: %d%%", device_id, battery)
            return battery

    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode Telemetry payload: %s", exc)
    return None


def _get_cached_battery(device_id: str | None) -> int | None:
    """Return cached battery level for a device, or None if stale/missing."""
    if not device_id or device_id not in _battery_cache:
        return None
    battery, cached_at = _battery_cache[device_id]
    if time.time() - cached_at > _BATTERY_CACHE_MAX_AGE_S:
        del _battery_cache[device_id]
        return None
    return battery


def _parse_protobuf_node_info(raw: bytes) -> dict[str, str | None]:
    """Decode the small subset of User/NodeInfo fields useful for debugging."""
    try:
        fields = _parse_protobuf_fields(raw)
    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode NodeInfo payload: %s", exc)
        return {"device_id": None, "long_name": None, "short_name": None}

    return {
        "device_id": _normalize_mesh_node_id(_decode_string(_get_bytes(fields, 1))),
        "long_name": _decode_string(_get_bytes(fields, 2)),
        "short_name": _decode_string(_get_bytes(fields, 3)),
    }


def _status_details_from_decoded(decoded: DecodedMeshEnvelope) -> dict[str, object | None]:
    device_id = _format_node_id(decoded.from_node)
    packet_type = "ENCRYPTED_APP" if decoded.encrypted and not decoded.decrypted else _packet_type_for_portnum(decoded.portnum)
    battery_level: int | None = None
    long_name: str | None = None
    short_name: str | None = None

    if decoded.portnum == 67 and decoded.payload_bytes:
        battery_level = _parse_protobuf_telemetry(decoded.payload_bytes, decoded.from_node)
    elif decoded.portnum == 4 and decoded.payload_bytes:
        node_info = _parse_protobuf_node_info(decoded.payload_bytes)
        device_id = node_info.get("device_id") or device_id
        long_name = node_info.get("long_name")
        short_name = node_info.get("short_name")

    return {
        "device_id": _normalize_mesh_node_id(device_id),
        "packet_type": packet_type,
        "battery_level": battery_level,
        "long_name": long_name,
        "short_name": short_name,
    }


def _record_mesh_node_status(
    session,
    *,
    device_id: str | None,
    packet_type: str,
    seen_at: datetime,
    gateway_id: str | None = None,
    topic: str | None = None,
    battery_level: int | None = None,
    long_name: str | None = None,
    short_name: str | None = None,
) -> MeshNodeStatus | None:
    normalized = _normalize_mesh_node_id(device_id)
    if normalized is None:
        return None

    status = session.scalar(select(MeshNodeStatus).where(MeshNodeStatus.device_id == normalized))
    if status is None:
        status = MeshNodeStatus(
            device_id=normalized,
            last_seen_at=seen_at,
            packet_count=0,
        )
    status.last_seen_at = seen_at
    status.last_packet_type = packet_type
    status.last_source = "mqtt_gateway"
    status.last_gateway_id = _normalize_mesh_node_id(gateway_id)
    status.last_topic = topic[:255] if topic else None
    status.packet_count = (status.packet_count or 0) + 1
    if battery_level is not None:
        status.battery_level = battery_level
        status.battery_level_seen_at = seen_at
    if long_name:
        status.long_name = long_name[:160]
    if short_name:
        status.short_name = short_name[:40]
    session.add(status)
    return status


def _parse_protobuf_position(raw: bytes | None = None, decoded: DecodedMeshEnvelope | None = None) -> dict | None:
    """Try to decode a Meshtastic protobuf ServiceEnvelope and extract a
    POSITION_APP payload.  Also processes TELEMETRY_APP messages to cache
    battery levels for later injection.

    Returns the same dict format as :func:`_parse_position` on success, or
    ``None`` if the message is not a valid position envelope.
    """
    if decoded is None and raw is not None:
        decoded = _decode_mesh_envelope(raw)
    if decoded is None:
        return None

    from_node = decoded.from_node
    portnum = decoded.portnum
    payload_bytes = decoded.payload_bytes
    device_id = _format_node_id(from_node)

    # Handle TELEMETRY_APP (portnum 67) — cache battery, no position to return
    if portnum == 67 and payload_bytes:
        _parse_protobuf_telemetry(payload_bytes, from_node)
        return None

    # Only process POSITION_APP (portnum 3)
    if portnum != 3:
        logger.debug("Protobuf Data portnum=%s, not POSITION_APP(3) or TELEMETRY_APP(67) -- skipping", portnum)
        return None

    if payload_bytes is None:
        return None

    try:
        # -- Position --------------------------------------------------------
        pos_fields = _parse_protobuf_fields(payload_bytes)

        # latitude_i  = field 1, sfixed32 (wire type 5)
        lat_i = _get_sfixed32(pos_fields, 1)
        # longitude_i = field 2, sfixed32 (wire type 5)
        lon_i = _get_sfixed32(pos_fields, 2)

        if lat_i is None or lon_i is None:
            logger.debug("Protobuf Position missing lat/lon fields")
            return None

        lat = lat_i / 1e7
        lon = lon_i / 1e7

        # Sanity check
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            logger.debug("Protobuf Position lat/lon out of range: %s, %s", lat, lon)
            return None

        # altitude = field 3 (int32 MSL) or altitude_hae = field 9 (sint32).
        alt_raw = _get_int32(pos_fields, 3)
        if alt_raw is None:
            alt_raw = _get_sint32(pos_fields, 9)
        alt = plausible_live_altitude_or_none(alt_raw)

        # timestamp = field 7, actual GPS solution timestamp. Field 4 is a
        # fallback time value commonly present in older/smaller packets.
        timestamp_raw = _get_uint32(pos_fields, 7)
        time_raw = _get_uint32(pos_fields, 4)
        fix_time_raw = timestamp_raw or time_raw
        ts = datetime.fromtimestamp(fix_time_raw, tz=UTC) if fix_time_raw else None

        # ground_speed = field 15, uint32 (varint) -- m/s
        speed_raw = _get_varint(pos_fields, 15)
        speed = float(speed_raw) if speed_raw is not None else None

        # ground_track = field 16, uint32 (varint) -- degrees * 1/100
        heading_raw = _get_varint(pos_fields, 16)
        heading = heading_raw / 100 if heading_raw is not None else None

        seq_number = _get_varint(pos_fields, 22)

        # Battery: use cached value from most recent TELEMETRY_APP message
        battery = _get_cached_battery(device_id)

        logger.debug(
            "Decoded protobuf position: device=%s lat=%.6f lon=%.6f alt=%s speed=%s heading=%s battery=%s",
            device_id, lat, lon, alt, speed, heading, battery,
        )

        return {
            "task_id": None,  # Meshtastic doesn't know about Aervyx tasks
            "lat": lat,
            "lon": lon,
            "alt": alt,
            "speed": speed,
            "heading": heading,
            "accuracy": None,
            "timestamp": ts,
            "source": "mqtt_gateway",
            "device_id": device_id,
            "mesh_seq_number": seq_number,
            "battery_level": battery,
            "pilot_id": None,
        }

    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode protobuf Position: %s", exc)
        return None


def _resolve_mesh_user(session, device_id: str | None) -> User | None:
    """Return the active tracking user assigned to a mesh device ID."""
    user, _device = resolve_mesh_device_assignment(session, device_id)
    return user


def _read_mqtt_config_from_db() -> tuple[str | None, int, str, str | None, str | None, bool]:
    """Read MQTT broker settings from the site_settings DB row.

    Returns ``(host, port, topic_prefix, username, password, tls_enabled)``.  If the row
    doesn't exist or MQTT is disabled, ``host`` will be ``None``.
    """
    session = SessionLocal()
    try:
        site = session.get(SiteSettings, 1)
        if site is None or not site.mqtt_enabled:
            return None, 1883, "msh", None, None, False
        broker_mode = normalize_mqtt_broker_mode(site.mqtt_broker_mode)
        changed = site.mqtt_broker_mode != broker_mode
        site.mqtt_broker_mode = broker_mode
        changed = clear_legacy_public_mqtt_values(site) or changed
        if changed:
            session.add(site)
            session.commit()
            session.refresh(site)
        settings = get_settings()
        if broker_mode == LOCAL_MOSQUITTO:
            return (
                getattr(settings, "mqtt_host", None) or "mosquitto",
                getattr(settings, "mqtt_port", 1883),
                site.mqtt_topic_prefix,
                None,
                None,
                False,
            )

        return (
            site.mqtt_host,
            site.mqtt_port,
            site.mqtt_topic_prefix,
            site.mqtt_username,
            site.mqtt_password,
            site.mqtt_tls_enabled,
        )
    finally:
        session.close()


def prune_old_mqtt_positions(retention_days: int | None = None) -> int:
    """Backward-compatible wrapper for the global live-position retention rule."""
    return prune_old_live_positions(retention_days=retention_days)


def request_mqtt_reconnect() -> None:
    """Ask the subscriber thread to refresh broker settings and device topics."""
    if mqtt_reconnect_event is not None:
        mqtt_reconnect_event.set()


def _handle_message(payload: bytes, topic: str | None = None) -> None:
    """Process a single MQTT message payload."""
    parsed = _parse_position(payload)
    decoded: DecodedMeshEnvelope | None = None
    if parsed is None:
        decoded = _decode_mesh_envelope(payload, _read_mqtt_channel_psks_from_db())
        if decoded is None:
            return
        parsed = _parse_protobuf_position(decoded=decoded)
    if parsed is None and decoded is None:
        return

    global mqtt_last_message_at
    seen_at = datetime.now(UTC)

    session = SessionLocal()
    try:
        if parsed is not None and decoded is None:
            _record_mesh_node_status(
                session,
                device_id=parsed.get("device_id"),
                packet_type="POSITION_APP",
                seen_at=seen_at,
                topic=topic,
                battery_level=parsed.get("battery_level"),
            )

        if decoded is not None:
            gateway_id = _gateway_id_from_topic(topic) or decoded.gateway_id
            details = _status_details_from_decoded(decoded)
            packet_type = str(details["packet_type"])
            sender_id = _normalize_mesh_node_id(details.get("device_id") if isinstance(details.get("device_id"), str) else None)

            if gateway_id is not None:
                _record_mesh_node_status(
                    session,
                    device_id=gateway_id,
                    packet_type=packet_type,
                    seen_at=seen_at,
                    gateway_id=gateway_id,
                    topic=topic,
                    battery_level=details.get("battery_level") if sender_id == gateway_id and isinstance(details.get("battery_level"), int) else None,
                    long_name=details.get("long_name") if sender_id == gateway_id and isinstance(details.get("long_name"), str) else None,
                    short_name=details.get("short_name") if sender_id == gateway_id and isinstance(details.get("short_name"), str) else None,
                )
            if sender_id is not None and sender_id != gateway_id:
                _record_mesh_node_status(
                    session,
                    device_id=sender_id,
                    packet_type=packet_type,
                    seen_at=seen_at,
                    gateway_id=gateway_id,
                    topic=topic,
                    battery_level=details.get("battery_level") if isinstance(details.get("battery_level"), int) else None,
                    long_name=details.get("long_name") if isinstance(details.get("long_name"), str) else None,
                    short_name=details.get("short_name") if isinstance(details.get("short_name"), str) else None,
                )

        if parsed is not None:
            mesh_user, mesh_device = resolve_mesh_device_assignment(session, parsed.get("device_id"))
            if mesh_user is not None or mesh_device is not None:
                mesh_profile_type = mesh_purpose_to_profile_type(mesh_device.purpose) if mesh_device is not None else None
                parsed["user_id"] = mesh_user.id if mesh_user is not None else None
                parsed["pilot_id"] = (
                    mesh_user.pilot_id
                    if mesh_user is not None
                    and (mesh_user.profile_type or "pilot").strip().lower() != "driver"
                    and mesh_profile_type != "driver"
                    else None
                )
                if parsed.get("task_id") is None and mesh_user is not None:
                    parsed["task_id"] = resolve_active_task_id_for_user(session, mesh_user)
                elif parsed.get("task_id") is None and parsed.get("pilot_id") is not None:
                    parsed["task_id"] = resolve_active_task_id(session, parsed["pilot_id"])
                store_position(session, **parsed)
        session.commit()
        mqtt_last_message_at = seen_at
    except Exception:
        logger.exception("Failed to process MQTT message")
        session.rollback()
    finally:
        session.close()


def _paho_subscribe_loop() -> None:
    """Blocking loop using paho-mqtt (runs in a daemon thread)."""
    global mqtt_connected

    while True:
        host, port, topic_prefix, username, password, tls_enabled = _read_mqtt_config_from_db()
        if not host:
            print("[MQTT] Not configured or disabled — sleeping 30s", flush=True)
            mqtt_connected = False
            time.sleep(30)
            continue

        topics = [(f"{topic_prefix}/#", 0)]
        topic_description = f"{topic_prefix}/#"
        print(f"[MQTT] Connecting to {host}:{port} topic={topic_description} user={username}", flush=True)

        # Explicit VERSION1 callback API for paho-mqtt 2.x compatibility
        try:
            from paho.mqtt.enums import CallbackAPIVersion
            client = paho_mqtt.Client(
                callback_api_version=CallbackAPIVersion.VERSION1,
                client_id=f"aervyx-{int(time.time()) % 100000}",
            )
        except ImportError:
            # Fallback for paho-mqtt 1.x
            client = paho_mqtt.Client(client_id=f"aervyx-{int(time.time()) % 100000}")

        if username:
            client.username_pw_set(username, password)
        if tls_enabled:
            client.tls_set()

        connected_event = threading.Event()

        def on_connect(client, userdata, flags, rc):
            global mqtt_connected
            print(f"[MQTT] on_connect: rc={rc} flags={flags}", flush=True)
            if rc == 0:
                mqtt_connected = True
                client.subscribe(topics)
                connected_event.set()
                print(f"[MQTT] Subscribed to {topic_description}", flush=True)
            else:
                print(f"[MQTT] CONNECT REFUSED rc={rc}", flush=True)

        def on_disconnect(client, userdata, rc):
            global mqtt_connected
            mqtt_connected = False
            print(f"[MQTT] Disconnected rc={rc}", flush=True)

        _msg_count = [0]

        def on_message(client, userdata, msg):
            _msg_count[0] += 1
            if _msg_count[0] <= 3 or _msg_count[0] % 100 == 0:
                print(f"[MQTT] Message #{_msg_count[0]}: {msg.topic} ({len(msg.payload)} bytes)", flush=True)
            payload = msg.payload
            if isinstance(payload, (bytes, bytearray)):
                _handle_message(payload, topic=getattr(msg, "topic", None))

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message

        try:
            client.connect(host, port, keepalive=60)
            client.loop_start()

            # Wait for CONNACK with timeout instead of polling is_connected()
            if not connected_event.wait(timeout=15):
                print("[MQTT] Timed out waiting for CONNACK after 15s", flush=True)
                client.loop_stop()
                try:
                    client.disconnect()
                except Exception:
                    pass
                time.sleep(5)
                continue

            print("[MQTT] Connected and subscribed, monitoring…", flush=True)

            # Stay connected; check for reconnect signal
            while True:
                time.sleep(5)
                if not client.is_connected():
                    print("[MQTT] Connection lost, will reconnect", flush=True)
                    break
                if mqtt_reconnect_event is not None and mqtt_reconnect_event.is_set():
                    mqtt_reconnect_event.clear()
                    print("[MQTT] Settings changed — reconnecting…", flush=True)
                    break
            client.loop_stop()
        except Exception as exc:
            mqtt_connected = False
            print(f"[MQTT] Connection error: {exc}", flush=True)
        finally:
            try:
                client.disconnect()
            except Exception:
                pass

        time.sleep(5)


async def start_mqtt_subscriber() -> None:
    """Launch the MQTT subscriber as a background daemon thread.

    Uses paho-mqtt directly for reliable connections to the configured
    private Meshtastic MQTT broker.
    """
    global mqtt_reconnect_event
    mqtt_reconnect_event = threading.Event()
    thread = threading.Thread(target=_paho_subscribe_loop, daemon=True)
    thread.start()
    logger.info("MQTT subscriber background thread started")
