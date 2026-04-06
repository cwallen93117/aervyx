"""Async HTTP wrapper for the Valhalla routing engine."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import httpx

from app.core.config import get_settings

_logger = logging.getLogger(__name__)

_TIMEOUT = 5.0  # seconds


@dataclass
class MatrixEntry:
    time: float  # seconds
    distance: float  # km


@dataclass
class ValhallaManeuver:
    instruction: str
    length: float  # km
    time: float  # seconds
    type: int
    street_name: str | None
    begin_shape_index: int
    end_shape_index: int


@dataclass
class ValhallaLeg:
    maneuvers: list[ValhallaManeuver]
    length: float  # km
    time: float  # seconds
    shape: str  # encoded polyline


@dataclass
class ValhallaRoute:
    legs: list[ValhallaLeg]
    length: float  # km
    time: float  # seconds
    shape: str  # full trip shape


def _valhalla_location(lat: float, lon: float) -> dict:
    return {"lat": lat, "lon": lon}


async def get_route(
    locations: list[tuple[float, float]],
    costing: str = "auto",
) -> ValhallaRoute | None:
    """Get ordered route with turn-by-turn directions.

    locations: list of (lat, lon) tuples in visit order.
    Returns None if Valhalla is unreachable.
    """
    if len(locations) < 2:
        return None

    settings = get_settings()
    body = {
        "locations": [_valhalla_location(lat, lon) for lat, lon in locations],
        "costing": costing,
        "directions_options": {"units": "kilometers"},
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(f"{settings.valhalla_url}/route", json=body)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        _logger.warning("Valhalla route request failed: %s", exc)
        return None

    trip = data.get("trip", {})
    legs: list[ValhallaLeg] = []
    for leg_data in trip.get("legs", []):
        maneuvers = [
            ValhallaManeuver(
                instruction=m.get("instruction", ""),
                length=m.get("length", 0),
                time=m.get("time", 0),
                type=m.get("type", 0),
                street_name=(m.get("street_names") or [None])[0],
                begin_shape_index=m.get("begin_shape_index", 0),
                end_shape_index=m.get("end_shape_index", 0),
            )
            for m in leg_data.get("maneuvers", [])
        ]
        legs.append(
            ValhallaLeg(
                maneuvers=maneuvers,
                length=leg_data.get("summary", {}).get("length", 0),
                time=leg_data.get("summary", {}).get("time", 0),
                shape=leg_data.get("shape", ""),
            )
        )

    summary = trip.get("summary", {})
    return ValhallaRoute(
        legs=legs,
        length=summary.get("length", 0),
        time=summary.get("time", 0),
        shape=trip.get("legs", [{}])[0].get("shape", "") if legs else "",
    )


async def get_matrix(
    sources: list[tuple[float, float]],
    targets: list[tuple[float, float]],
    costing: str = "auto",
) -> list[list[MatrixEntry]] | None:
    """Get time/distance matrix between sources and targets.

    Returns a 2D list: result[source_idx][target_idx].
    Returns None if Valhalla is unreachable.
    """
    settings = get_settings()
    body = {
        "sources": [_valhalla_location(lat, lon) for lat, lon in sources],
        "targets": [_valhalla_location(lat, lon) for lat, lon in targets],
        "costing": costing,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{settings.valhalla_url}/sources_to_targets", json=body
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        _logger.warning("Valhalla matrix request failed: %s", exc)
        return None

    rows = data.get("sources_to_targets", [])
    matrix: list[list[MatrixEntry]] = []
    for row in rows:
        matrix.append(
            [
                MatrixEntry(
                    time=cell.get("time", 0),
                    distance=cell.get("distance", 0),
                )
                for cell in row
            ]
        )
    return matrix


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance fallback when Valhalla is unavailable."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_matrix(
    sources: list[tuple[float, float]],
    targets: list[tuple[float, float]],
    avg_speed_kmh: float = 40.0,
) -> list[list[MatrixEntry]]:
    """Straight-line distance matrix fallback with estimated driving time."""
    matrix: list[list[MatrixEntry]] = []
    for slat, slon in sources:
        row: list[MatrixEntry] = []
        for tlat, tlon in targets:
            dist = haversine_km(slat, slon, tlat, tlon)
            # Rough driving estimate: 1.4x straight-line distance at avg_speed
            road_dist = dist * 1.4
            time_s = (road_dist / avg_speed_kmh) * 3600
            row.append(MatrixEntry(time=time_s, distance=road_dist))
        matrix.append(row)
    return matrix
