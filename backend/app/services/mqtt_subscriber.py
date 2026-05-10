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

import json
import logging
import struct
import threading
import time
from datetime import UTC, datetime

import paho.mqtt.client as paho_mqtt
from sqlalchemy import select

from app.db import SessionLocal
from app.models import MeshDevice, SiteSettings, User
from app.services.tracking import (
    LIVE_POSITION_RETENTION_DAYS,
    prune_old_live_positions,
    resolve_active_task_id,
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


def _decode_mesh_envelope(raw: bytes) -> tuple[int | None, int | None, bytes | None] | None:
    """Decode a Meshtastic ServiceEnvelope → MeshPacket → Data.

    Returns ``(from_node, portnum, payload_bytes)`` or ``None`` on failure.
    """
    try:
        envelope_fields = _parse_protobuf_fields(raw)
        mesh_packet_bytes = _get_bytes(envelope_fields, 1)
        if mesh_packet_bytes is None:
            return None

        mp_fields = _parse_protobuf_fields(mesh_packet_bytes)
        from_node = _get_fixed32(mp_fields, 1)

        data_bytes = _get_bytes(mp_fields, 3)
        if data_bytes is None:
            logger.debug("Protobuf MeshPacket has no decoded Data (probably encrypted)")
            return None

        data_fields = _parse_protobuf_fields(data_bytes)
        portnum = _get_varint(data_fields, 1)
        payload_bytes = _get_bytes(data_fields, 2)

        return from_node, portnum, payload_bytes
    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode protobuf ServiceEnvelope: %s", exc)
        return None


def _parse_protobuf_telemetry(raw: bytes, from_node: int | None) -> None:
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
        return

    try:
        telemetry_fields = _parse_protobuf_fields(raw)

        # Field 2 = device_metrics (length-delimited)
        metrics_bytes = _get_bytes(telemetry_fields, 2)
        if metrics_bytes is None:
            # Could be environment_metrics or power_metrics — not device_metrics
            return

        metrics_fields = _parse_protobuf_fields(metrics_bytes)

        # Field 1 = battery_level (uint32)
        battery = _get_varint(metrics_fields, 1)
        if battery is not None and 0 <= battery <= 100:
            _battery_cache[device_id] = (battery, time.time())
            logger.debug("Cached battery for %s: %d%%", device_id, battery)

    except (ValueError, struct.error, IndexError, KeyError) as exc:
        logger.debug("Failed to decode Telemetry payload: %s", exc)


def _get_cached_battery(device_id: str | None) -> int | None:
    """Return cached battery level for a device, or None if stale/missing."""
    if not device_id or device_id not in _battery_cache:
        return None
    battery, cached_at = _battery_cache[device_id]
    if time.time() - cached_at > _BATTERY_CACHE_MAX_AGE_S:
        del _battery_cache[device_id]
        return None
    return battery


def _parse_protobuf_position(raw: bytes) -> dict | None:
    """Try to decode a Meshtastic protobuf ServiceEnvelope and extract a
    POSITION_APP payload.  Also processes TELEMETRY_APP messages to cache
    battery levels for later injection.

    Returns the same dict format as :func:`_parse_position` on success, or
    ``None`` if the message is not a valid position envelope.
    """
    decoded = _decode_mesh_envelope(raw)
    if decoded is None:
        return None

    from_node, portnum, payload_bytes = decoded
    device_id = f"!{from_node:08x}" if from_node is not None else None

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

        # altitude = field 3 (int32, legacy) or altitude_hae = field 11 (int32, preferred)
        # Many devices populate only field 11 (height above ellipsoid).
        alt_raw = _get_varint(pos_fields, 3)
        if alt_raw is None:
            alt_raw = _get_varint(pos_fields, 11)
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


def _read_registered_mesh_device_ids_from_db() -> list[str]:
    """Return active platform mesh device IDs for targeted public MQTT subscriptions."""
    session = SessionLocal()
    try:
        device_ids = set(
            session.scalars(
                select(MeshDevice.device_id)
                .join(User, User.id == MeshDevice.owner_user_id)
                .where(
                    MeshDevice.is_active.is_(True),
                    MeshDevice.device_id.isnot(None),
                    MeshDevice.device_id != "",
                    User.is_active.is_(True),
                )
            ).all()
        )
        device_ids.update(
            session.scalars(
                select(User.mesh_device_id)
                .where(
                    User.is_active.is_(True),
                    User.mesh_device_id.isnot(None),
                    User.mesh_device_id != "",
                )
            ).all()
        )
        return sorted(device_ids)
    finally:
        session.close()


def _read_mqtt_config_from_db() -> tuple[str | None, int, str, str | None, str | None]:
    """Read MQTT broker settings from the site_settings DB row.

    Returns ``(host, port, topic_prefix, username, password)``.  If the row
    doesn't exist or MQTT is disabled, ``host`` will be ``None``.
    """
    session = SessionLocal()
    try:
        site = session.get(SiteSettings, 1)
        if site is None or not site.mqtt_enabled:
            return None, 1883, "msh", None, None
        is_public = site.mqtt_broker_mode == "public"
        host = "mqtt.meshtastic.org" if is_public else site.mqtt_host
        # Public Meshtastic broker requires well-known credentials
        username = "meshdev" if is_public else None
        password = "large4cats" if is_public else None
        return host, site.mqtt_port, site.mqtt_topic_prefix, username, password
    finally:
        session.close()


def prune_old_mqtt_positions(retention_days: int = LIVE_POSITION_RETENTION_DAYS) -> int:
    """Backward-compatible wrapper for the global live-position retention rule."""
    return prune_old_live_positions(retention_days=retention_days)


def request_mqtt_reconnect() -> None:
    """Ask the subscriber thread to refresh broker settings and device topics."""
    if mqtt_reconnect_event is not None:
        mqtt_reconnect_event.set()


def _handle_message(payload: bytes) -> None:
    """Process a single MQTT message payload."""
    parsed = _parse_position(payload)
    if parsed is None:
        parsed = _parse_protobuf_position(payload)
    if parsed is None:
        return

    global mqtt_last_message_at

    session = SessionLocal()
    try:
        mesh_user, mesh_device = resolve_mesh_device_assignment(session, parsed.get("device_id"))
        if mesh_user is None and mesh_device is None:
            return

        parsed["pilot_id"] = mesh_user.pilot_id if mesh_user is not None else None
        if parsed.get("task_id") is None and parsed.get("pilot_id") is not None:
            parsed["task_id"] = resolve_active_task_id(session, parsed["pilot_id"])
        store_position(session, **parsed)
        session.commit()
        mqtt_last_message_at = datetime.now(UTC)
    except Exception:
        logger.exception("Failed to store MQTT position")
        session.rollback()
    finally:
        session.close()


def _paho_subscribe_loop() -> None:
    """Blocking loop using paho-mqtt (runs in a daemon thread)."""
    global mqtt_connected

    while True:
        host, port, topic_prefix, username, password = _read_mqtt_config_from_db()
        if not host:
            print("[MQTT] Not configured or disabled — sleeping 30s", flush=True)
            mqtt_connected = False
            time.sleep(30)
            continue

        # For the public Meshtastic broker, avoid the full LongFast firehose:
        # subscribe directly to each registered device's topic.
        if host == "mqtt.meshtastic.org":
            registered_device_ids = _read_registered_mesh_device_ids_from_db()
            if not registered_device_ids:
                print("[MQTT] Public broker enabled, but no registered mesh devices - sleeping 30s", flush=True)
                mqtt_connected = False
                time.sleep(30)
                continue
            topics = [(f"{topic_prefix}/US/2/e/LongFast/{device_id}", 0) for device_id in registered_device_ids]
            topic_description = f"{len(topics)} registered device topic(s)"
        else:
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
                _handle_message(payload)

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

    Uses paho-mqtt directly for reliable connections to the public
    Meshtastic broker.
    """
    global mqtt_reconnect_event
    mqtt_reconnect_event = threading.Event()
    thread = threading.Thread(target=_paho_subscribe_loop, daemon=True)
    thread.start()
    logger.info("MQTT subscriber background thread started")
