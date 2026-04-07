"""Server-side landing detection for pilot positions.

Maintains an in-memory buffer of recent positions per (task_id, pilot_id)
and confirms landings when speed stays below threshold for a sustained period.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PilotLanding

_logger = logging.getLogger(__name__)

# Detection thresholds (match client-side config)
LANDING_SPEED_MS = 4.47
LANDING_ALTITUDE_TOLERANCE_M = 30.5
LANDING_CONFIRM_SECONDS = 15
READY_DELAY_MINUTES = 30

# If pilot resumes above this speed, cancel the landing
RESUME_SPEED_MS = 6.0

# Maximum buffer entries per pilot (prevents memory leaks)
MAX_BUFFER_SIZE = 60


@dataclass
class PositionSample:
    lat: float
    lon: float
    alt: float | None
    speed: float | None
    timestamp: datetime


@dataclass
class PilotBuffer:
    samples: list[PositionSample] = field(default_factory=list)
    landing_candidate_start: datetime | None = None
    confirmed_landing_id: int | None = None


# In-memory state keyed by (task_id, pilot_id)
_buffers: dict[tuple[int, int], PilotBuffer] = defaultdict(PilotBuffer)


def reset_buffers() -> None:
    """Clear all buffers (for testing)."""
    _buffers.clear()


def check_landing(
    session: Session,
    task_id: int,
    pilot_id: int,
    lat: float,
    lon: float,
    alt: float | None,
    speed: float | None,
    timestamp: datetime,
) -> dict | None:
    """Check if this position indicates a landing or flight resumption.

    Returns a dict suitable for SSE broadcast if a landing event occurred,
    or None if no state change.
    """
    key = (task_id, pilot_id)
    buf = _buffers[key]

    sample = PositionSample(
        lat=lat, lon=lon, alt=alt, speed=speed, timestamp=timestamp
    )
    buf.samples.append(sample)

    # Trim buffer to prevent unbounded growth
    if len(buf.samples) > MAX_BUFFER_SIZE:
        buf.samples = buf.samples[-MAX_BUFFER_SIZE:]

    # If pilot already has a confirmed landing, check for flight resumption
    if buf.confirmed_landing_id is not None:
        if speed is not None and speed > RESUME_SPEED_MS:
            return _cancel_landing(session, buf, key)
        return None

    # Check for landing candidate
    if speed is not None and speed < LANDING_SPEED_MS:
        if buf.landing_candidate_start is None:
            buf.landing_candidate_start = timestamp
        else:
            elapsed = (timestamp - buf.landing_candidate_start).total_seconds()
            if elapsed >= LANDING_CONFIRM_SECONDS:
                # Verify altitude stability within the confirmation window
                if _altitude_stable(buf, timestamp):
                    return _confirm_landing(session, buf, key, lat, lon, alt, timestamp)
    else:
        # Speed above threshold, reset candidate
        buf.landing_candidate_start = None

    return None


def _altitude_stable(buf: PilotBuffer, now: datetime) -> bool:
    """Check altitude stayed within tolerance during the confirmation window."""
    cutoff = now - timedelta(seconds=LANDING_CONFIRM_SECONDS)
    window_samples = [s for s in buf.samples if s.timestamp >= cutoff and s.alt is not None]
    if not window_samples:
        return True  # No altitude data available, accept landing
    alts = [s.alt for s in window_samples]
    return (max(alts) - min(alts)) <= LANDING_ALTITUDE_TOLERANCE_M


def _confirm_landing(
    session: Session,
    buf: PilotBuffer,
    key: tuple[int, int],
    lat: float,
    lon: float,
    alt: float | None,
    timestamp: datetime,
) -> dict:
    task_id, pilot_id = key
    landed_at = buf.landing_candidate_start or timestamp
    ready_at = landed_at + timedelta(minutes=READY_DELAY_MINUTES)

    # Check for existing active landing for this pilot+task
    existing = session.scalars(
        select(PilotLanding).where(
            PilotLanding.task_id == task_id,
            PilotLanding.pilot_id == pilot_id,
            PilotLanding.status.in_(["landed", "ready"]),
        )
    ).first()

    if existing is not None:
        # Already have an active landing, don't duplicate
        buf.confirmed_landing_id = existing.id
        return None

    landing = PilotLanding(
        task_id=task_id,
        pilot_id=pilot_id,
        landed_at=landed_at,
        ready_at=ready_at,
        lat=lat,
        lon=lon,
        alt=alt,
        status="landed",
    )
    session.add(landing)
    session.flush()

    buf.confirmed_landing_id = landing.id
    _logger.info(
        "Landing confirmed: pilot %d task %d at (%.6f, %.6f), ready at %s",
        pilot_id, task_id, lat, lon, ready_at.isoformat(),
    )

    return {
        "event": "landing",
        "pilot_id": pilot_id,
        "landing_id": landing.id,
        "lat": lat,
        "lon": lon,
        "alt": alt,
        "landed_at": landed_at.isoformat(),
        "ready_at": ready_at.isoformat(),
    }


def _cancel_landing(
    session: Session,
    buf: PilotBuffer,
    key: tuple[int, int],
) -> dict | None:
    task_id, pilot_id = key
    landing_id = buf.confirmed_landing_id

    if landing_id is not None:
        landing = session.get(PilotLanding, landing_id)
        if landing is not None and landing.status in ("landed", "ready"):
            landing.status = "cancelled"
            session.flush()
            _logger.info(
                "Landing cancelled: pilot %d task %d (resumed flying)",
                pilot_id, task_id,
            )

    # Reset buffer state
    buf.confirmed_landing_id = None
    buf.landing_candidate_start = None

    return {
        "event": "landing_cancelled",
        "pilot_id": pilot_id,
        "landing_id": landing_id,
    }
