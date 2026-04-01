"""Background MQTT subscriber for Meshtastic position messages.

Connects to the Mosquitto broker, subscribes to ``<prefix>/#`` and persists
incoming position reports into the ``live_positions`` table with
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

import asyncio
import json
import logging
import struct
from datetime import UTC, datetime

import aiomqtt

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.tracking import store_position

logger = logging.getLogger("aervyx.mqtt")

# Module-level state exposed for the admin debug endpoint
mqtt_connected: bool = False
mqtt_last_message_at: datetime | None = None


def _parse_position(raw: bytes | bytearray) -> dict | None:
    """Try to parse a JSON position payload. Returns None on failure."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        logger.debug("Ignoring non-JSON MQTT message")
        return None

    if not isinstance(data, dict):
        return None

    # Require at minimum lat, lon, and task_id
    lat = data.get("latitude")
    lon = data.get("longitude")
    task_id = data.get("task_id")
    if lat is None or lon is None or task_id is None:
        logger.debug("Ignoring MQTT message missing latitude, longitude, or task_id")
        return None

    ts_raw = data.get("timestamp")
    ts = None
    if ts_raw:
        try:
            ts = datetime.fromisoformat(ts_raw)
        except (ValueError, TypeError):
            pass

    return {
        "task_id": int(task_id),
        "lat": float(lat),
        "lon": float(lon),
        "alt": float(data["altitude"]) if data.get("altitude") is not None else None,
        "speed": float(data["speed"]) if data.get("speed") is not None else None,
        "heading": float(data["heading"]) if data.get("heading") is not None else None,
        "accuracy": float(data["accuracy"]) if data.get("accuracy") is not None else None,
        "timestamp": ts,
        "source": "mqtt_gateway",
        "device_id": str(data["device_id"]) if data.get("device_id") is not None else None,
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


def _get_sfixed32(fields: dict, field_number: int) -> int | None:
    """Return the first sfixed32 (signed) value for *field_number*, or ``None``."""
    entries = fields.get(field_number)
    if not entries:
        return None
    wt, val = entries[0]
    if wt == 5 and isinstance(val, (bytes, bytearray)) and len(val) == 4:
        return struct.unpack("<i", val)[0]
    return None


def _parse_protobuf_position(raw: bytes) -> dict | None:
    """Try to decode a Meshtastic protobuf ServiceEnvelope and extract a
    POSITION_APP payload.

    Returns the same dict format as :func:`_parse_position` on success, or
    ``None`` if the message is not a valid position envelope.
    """
    try:
        # -- ServiceEnvelope -------------------------------------------------
        envelope_fields = _parse_protobuf_fields(raw)

        # Field 1 = MeshPacket (length-delimited)
        mesh_packet_bytes = _get_bytes(envelope_fields, 1)
        if mesh_packet_bytes is None:
            return None

        # -- MeshPacket ------------------------------------------------------
        mp_fields = _parse_protobuf_fields(mesh_packet_bytes)

        # Field 1 = from (fixed32, wire type 5)
        from_node = _get_fixed32(mp_fields, 1)

        # Field 3 = decoded Data (length-delimited) -- only present when not
        # encrypted
        data_bytes = _get_bytes(mp_fields, 3)
        if data_bytes is None:
            logger.debug("Protobuf MeshPacket has no decoded Data (probably encrypted)")
            return None

        # -- Data ------------------------------------------------------------
        data_fields = _parse_protobuf_fields(data_bytes)

        # Field 1 = portnum (varint).  POSITION_APP = 3
        portnum = _get_varint(data_fields, 1)
        if portnum != 3:
            logger.debug("Protobuf Data portnum=%s, not POSITION_APP(3) -- skipping", portnum)
            return None

        # Field 2 = payload (length-delimited, contains Position message)
        position_bytes = _get_bytes(data_fields, 2)
        if position_bytes is None:
            return None

        # -- Position --------------------------------------------------------
        pos_fields = _parse_protobuf_fields(position_bytes)

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

        # altitude = field 3, int32 (varint)
        alt_raw = _get_varint(pos_fields, 3)
        alt = float(alt_raw) if alt_raw is not None else None

        # time = field 4, int32 (varint) -- unix timestamp
        time_raw = _get_varint(pos_fields, 4)
        ts = datetime.fromtimestamp(time_raw, tz=UTC) if time_raw else None

        # ground_speed = field 8, uint32 (varint) -- m/s
        speed_raw = _get_varint(pos_fields, 8)
        speed = float(speed_raw) if speed_raw is not None else None

        # ground_track = field 9, uint32 (varint) -- degrees * 1e5
        heading_raw = _get_varint(pos_fields, 9)
        heading = heading_raw / 1e5 if heading_raw is not None else None

        # Build device_id from the MeshPacket ``from`` field
        device_id = f"!{from_node:08x}" if from_node is not None else None

        logger.debug(
            "Decoded protobuf position: device=%s lat=%.6f lon=%.6f alt=%s",
            device_id, lat, lon, alt,
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
            "battery_level": None,
            "pilot_id": None,
        }

    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode protobuf ServiceEnvelope: %s", exc)
        return None


async def _subscribe_loop(host: str, port: int, topic_prefix: str) -> None:
    """Connect to broker and process messages indefinitely."""
    topic = f"{topic_prefix}/#"
    logger.info("MQTT subscriber connecting to %s:%d topic %s", host, port, topic)

    global mqtt_connected, mqtt_last_message_at

    while True:
        try:
            async with aiomqtt.Client(hostname=host, port=port) as client:
                await client.subscribe(topic)
                mqtt_connected = True
                logger.info("MQTT subscribed to %s", topic)
                async for message in client.messages:
                    payload = message.payload
                    if not isinstance(payload, (bytes, bytearray)):
                        continue

                    # Try JSON first, then fall back to protobuf
                    parsed = _parse_position(payload)
                    if parsed is None:
                        parsed = _parse_protobuf_position(payload)

                    if parsed is None:
                        continue

                    session = SessionLocal()
                    try:
                        store_position(session, **parsed)
                        session.commit()
                        mqtt_last_message_at = datetime.now(UTC)
                    except Exception:
                        logger.exception("Failed to store MQTT position")
                        session.rollback()
                    finally:
                        session.close()

        except aiomqtt.MqttError as exc:
            mqtt_connected = False
            logger.warning("MQTT connection lost (%s), reconnecting in 5s…", exc)
            await asyncio.sleep(5)
        except Exception:
            mqtt_connected = False
            logger.exception("Unexpected MQTT error, reconnecting in 10s…")
            await asyncio.sleep(10)


async def start_mqtt_subscriber() -> asyncio.Task | None:
    """Launch the MQTT subscriber as a background asyncio task.

    Returns the task handle, or ``None`` if MQTT is not configured.
    """
    settings = get_settings()
    host = settings.mqtt_host
    if not host:
        logger.info("MQTT_HOST not set — MQTT subscriber disabled")
        return None

    port = settings.mqtt_port
    prefix = settings.mesh_mqtt_topic_prefix

    task = asyncio.create_task(_subscribe_loop(host, port, prefix))
    logger.info("MQTT subscriber background task started")
    return task
