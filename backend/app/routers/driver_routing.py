"""Driver routing API: multi-stop pickup routes with Valhalla turn-by-turn."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import get_current_user, require_staff
from app.models import (
    DriverAssignment,
    DriverPosition,
    EventPilot,
    Pilot,
    PilotLanding,
    Task,
    User,
)
from app.services.routing import schemas as rs
from app.services.routing.route_optimizer import OptimizedStop, PickupTarget, optimize_route
from app.services.routing.valhalla_client import (
    ValhallaRoute,
    get_matrix,
    get_route,
    haversine_matrix,
)

_logger = logging.getLogger(__name__)

router = APIRouter(tags=["driver-routing"])


# ---------- Pydantic request/response models ----------


class DriverPositionPayload(BaseModel):
    task_id: int | None = None
    lat: float
    lon: float
    heading: float | None = None
    speed: float | None = None
    accuracy: float | None = None
    timestamp: str | None = None


class DriverAssignmentPayload(BaseModel):
    driver_user_id: int
    pilot_ids: list[int]


class LandingInfo(BaseModel):
    landing_id: int
    landed_at: str
    ready_at: str
    lat: float
    lon: float
    status: str


class AssignedPilotResponse(BaseModel):
    pilot_id: int
    first_name: str
    last_name: str
    landing: LandingInfo | None = None


class LandingResponse(BaseModel):
    landing_id: int
    pilot_id: int
    pilot_name: str
    landed_at: str
    ready_at: str
    lat: float
    lon: float
    alt: float | None
    status: str
    picked_up_at: str | None


# ---------- Endpoints ----------


@router.get("/api/driver/route/{task_id}", response_model=rs.DriverRouteResponse)
async def get_driver_route(
    task_id: int,
    lat: float = Query(..., description="Driver current latitude"),
    lon: float = Query(..., description="Driver current longitude"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> rs.DriverRouteResponse:
    """Compute optimized multi-stop pickup route for the driver."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Get assigned pilots with active landings
    targets = _get_pickup_targets(session, task_id, user.id)
    if not targets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pilots awaiting pickup",
        )

    now = datetime.now(timezone.utc)

    # Build locations: driver first, then each target
    all_locations = [(lat, lon)] + [(t.lat, t.lon) for t in targets]

    # Get time/distance matrix from Valhalla (or fallback)
    matrix = await get_matrix(
        sources=all_locations,
        targets=[(t.lat, t.lon) for t in targets],
    )
    if matrix is None:
        _logger.warning("Valhalla unavailable, using haversine fallback")
        matrix = haversine_matrix(
            sources=all_locations,
            targets=[(t.lat, t.lon) for t in targets],
        )

    # Optimize stop order
    schedule = optimize_route(targets, matrix, now)

    # Get turn-by-turn route from Valhalla for the optimized order
    ordered_locations = [(lat, lon)] + [(s.target.lat, s.target.lon) for s in schedule]
    valhalla_route = await get_route(ordered_locations)

    # Build response
    stops = [
        rs.RouteStop(
            pilot_id=s.target.pilot_id,
            pilot_name=s.target.pilot_name,
            landing_id=s.target.landing_id,
            lat=s.target.lat,
            lon=s.target.lon,
            landed_at=s.target.landed_at.isoformat(),
            ready_at=s.target.ready_at.isoformat(),
            eta=s.eta.isoformat(),
            distance_km=s.distance_km,
            status=s.target.status,
        )
        for s in schedule
    ]

    legs: list[rs.RouteLeg] = []
    total_distance = 0.0
    total_time = 0

    if valhalla_route is not None:
        for i, vleg in enumerate(valhalla_route.legs):
            pilot_id = schedule[i].target.pilot_id if i < len(schedule) else 0
            maneuvers = [
                rs.RouteManeuver(
                    instruction=m.instruction,
                    distance_km=m.length,
                    time_seconds=int(m.time),
                    type=m.type,
                    street_name=m.street_name,
                    begin_shape_index=m.begin_shape_index,
                    end_shape_index=m.end_shape_index,
                )
                for m in vleg.maneuvers
            ]
            legs.append(
                rs.RouteLeg(
                    pilot_id=pilot_id,
                    maneuvers=maneuvers,
                    distance_km=vleg.length,
                    time_seconds=int(vleg.time),
                    shape=vleg.shape,
                )
            )
        total_distance = valhalla_route.length
        total_time = int(valhalla_route.time)
    else:
        # Fallback: no turn-by-turn, just distances from schedule
        for s in schedule:
            legs.append(
                rs.RouteLeg(
                    pilot_id=s.target.pilot_id,
                    maneuvers=[],
                    distance_km=s.distance_km,
                    time_seconds=int(s.travel_seconds),
                    shape="",
                )
            )
            total_distance += s.distance_km
            total_time += int(s.travel_seconds)

    return rs.DriverRouteResponse(
        stops=stops,
        legs=legs,
        total_distance_km=total_distance,
        total_time_seconds=total_time,
        shape=valhalla_route.shape if valhalla_route else "",
    )


@router.post("/api/driver/position", status_code=status.HTTP_201_CREATED)
def report_driver_position(
    payload: DriverPositionPayload,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Report driver vehicle position."""
    ts = (
        datetime.fromisoformat(payload.timestamp)
        if payload.timestamp
        else datetime.now(timezone.utc)
    )
    pos = DriverPosition(
        driver_user_id=user.id,
        task_id=payload.task_id,
        lat=payload.lat,
        lon=payload.lon,
        heading=payload.heading,
        speed=payload.speed,
        accuracy=payload.accuracy,
        timestamp=ts,
    )
    session.add(pos)
    session.commit()
    return {"status": "ok"}


@router.get("/api/driver/landings/{task_id}", response_model=list[LandingResponse])
def get_pilot_landings(
    task_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[LandingResponse]:
    """Get all pilot landings for a task with status info."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    landings = session.scalars(
        select(PilotLanding)
        .where(PilotLanding.task_id == task_id)
        .order_by(PilotLanding.landed_at.desc())
    ).all()

    result = []
    for landing in landings:
        pilot = session.get(Pilot, landing.pilot_id)
        pilot_name = f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown"
        result.append(
            LandingResponse(
                landing_id=landing.id,
                pilot_id=landing.pilot_id,
                pilot_name=pilot_name,
                landed_at=landing.landed_at.isoformat(),
                ready_at=landing.ready_at.isoformat(),
                lat=landing.lat,
                lon=landing.lon,
                alt=landing.alt,
                status=landing.status,
                picked_up_at=landing.picked_up_at.isoformat() if landing.picked_up_at else None,
            )
        )
    return result


@router.post("/api/driver/pickup/{landing_id}")
def mark_picked_up(
    landing_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Mark a pilot as picked up."""
    landing = session.get(PilotLanding, landing_id)
    if landing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Landing not found")
    if landing.status == "picked_up":
        return {"status": "already_picked_up"}

    landing.status = "picked_up"
    landing.picked_up_at = datetime.now(timezone.utc)
    landing.picked_up_by_user_id = user.id
    session.commit()
    return {"status": "ok"}


@router.post("/api/driver/cancel-pickup/{landing_id}")
def cancel_pickup(
    landing_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Undo a pickup (pilot decides to self-retrieve, etc.)."""
    landing = session.get(PilotLanding, landing_id)
    if landing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Landing not found")
    if landing.status != "picked_up":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not picked up")

    landing.status = "ready"
    landing.picked_up_at = None
    landing.picked_up_by_user_id = None
    session.commit()
    return {"status": "ok"}


@router.put("/api/admin/driver-assignments/{task_id}")
def set_driver_assignments(
    task_id: int,
    payload: DriverAssignmentPayload,
    user: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> dict:
    """Assign pilots to a driver for a task (replaces existing assignments)."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    # Delete existing assignments for this driver+task
    existing = session.scalars(
        select(DriverAssignment).where(
            DriverAssignment.task_id == task_id,
            DriverAssignment.driver_user_id == payload.driver_user_id,
        )
    ).all()
    for a in existing:
        session.delete(a)

    # Insert new assignments
    for pilot_id in payload.pilot_ids:
        session.add(
            DriverAssignment(
                task_id=task_id,
                driver_user_id=payload.driver_user_id,
                pilot_id=pilot_id,
            )
        )
    session.commit()
    return {"status": "ok", "count": len(payload.pilot_ids)}


@router.get("/api/admin/driver-assignments/{task_id}")
def get_driver_assignments(
    task_id: int,
    user: User = Depends(require_staff),
    session: Session = Depends(get_session),
) -> list[dict]:
    """View all driver-pilot assignments for a task."""
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    assignments = session.scalars(
        select(DriverAssignment).where(DriverAssignment.task_id == task_id)
    ).all()

    result = []
    for a in assignments:
        pilot = session.get(Pilot, a.pilot_id)
        driver = session.get(User, a.driver_user_id)
        result.append({
            "id": a.id,
            "task_id": a.task_id,
            "driver_user_id": a.driver_user_id,
            "driver_name": driver.full_name if driver else "Unknown",
            "pilot_id": a.pilot_id,
            "pilot_name": f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown",
        })
    return result


# ---------- Helpers ----------


def _get_pickup_targets(
    session: Session,
    task_id: int,
    driver_user_id: int,
) -> list[PickupTarget]:
    """Get pilots assigned to this driver with active landings."""
    # Get assigned pilot IDs (or fall back to all event pilots)
    assigned_ids = session.scalars(
        select(DriverAssignment.pilot_id).where(
            DriverAssignment.task_id == task_id,
            DriverAssignment.driver_user_id == driver_user_id,
        )
    ).all()

    if not assigned_ids:
        # Fallback: all event pilots for backward compat
        task = session.get(Task, task_id)
        if task is None:
            return []
        assigned_ids = session.scalars(
            select(EventPilot.pilot_id).where(EventPilot.event_id == task.event_id)
        ).all()

    if not assigned_ids:
        return []

    # Get active landings for assigned pilots
    landings = session.scalars(
        select(PilotLanding).where(
            PilotLanding.task_id == task_id,
            PilotLanding.pilot_id.in_(assigned_ids),
            PilotLanding.status.in_(["landed", "ready"]),
        )
    ).all()

    targets: list[PickupTarget] = []
    for landing in landings:
        pilot = session.get(Pilot, landing.pilot_id)
        if pilot is None:
            continue
        targets.append(
            PickupTarget(
                pilot_id=landing.pilot_id,
                pilot_name=f"{pilot.first_name} {pilot.last_name}",
                landing_id=landing.id,
                lat=landing.lat,
                lon=landing.lon,
                ready_at=landing.ready_at,
                landed_at=landing.landed_at,
                status=landing.status,
            )
        )

    return targets
