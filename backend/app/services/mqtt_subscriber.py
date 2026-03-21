"""Background MQTT subscriber for Meshtastic position messages.

Connects to the Mosquitto broker, subscribes to ``<prefix>/#`` and persists
incoming position reports into the ``live_positions`` table with
``source='mqtt_gateway'``.

Meshtastic MQTT position payloads are expected as JSON with at minimum::

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
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import aiomqtt

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.tracking import store_position

logger = logging.getLogger("aervyx.mqtt")


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


async def _subscribe_loop(host: str, port: int, topic_prefix: str) -> None:
    """Connect to broker and process messages indefinitely."""
    topic = f"{topic_prefix}/#"
    logger.info("MQTT subscriber connecting to %s:%d topic %s", host, port, topic)

    while True:
        try:
            async with aiomqtt.Client(hostname=host, port=port) as client:
                await client.subscribe(topic)
                logger.info("MQTT subscribed to %s", topic)
                async for message in client.messages:
                    payload = message.payload
                    if isinstance(payload, (bytes, bytearray)):
                        parsed = _parse_position(payload)
                    else:
                        continue

                    if parsed is None:
                        continue

                    session = SessionLocal()
                    try:
                        store_position(session, **parsed)
                        session.commit()
                    except Exception:
                        logger.exception("Failed to store MQTT position")
                        session.rollback()
                    finally:
                        session.close()

        except aiomqtt.MqttError as exc:
            logger.warning("MQTT connection lost (%s), reconnecting in 5s…", exc)
            await asyncio.sleep(5)
        except Exception:
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
