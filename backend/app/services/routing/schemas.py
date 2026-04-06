from __future__ import annotations

from pydantic import BaseModel


class LatLon(BaseModel):
    lat: float
    lon: float


class RouteStop(BaseModel):
    pilot_id: int
    pilot_name: str
    landing_id: int
    lat: float
    lon: float
    landed_at: str
    ready_at: str
    eta: str
    distance_km: float
    status: str  # landed | ready | picked_up


class RouteManeuver(BaseModel):
    instruction: str
    distance_km: float
    time_seconds: int
    type: int
    street_name: str | None = None
    begin_shape_index: int
    end_shape_index: int


class RouteLeg(BaseModel):
    pilot_id: int
    maneuvers: list[RouteManeuver]
    distance_km: float
    time_seconds: int
    shape: str  # encoded polyline


class DriverRouteResponse(BaseModel):
    stops: list[RouteStop]
    legs: list[RouteLeg]
    total_distance_km: float
    total_time_seconds: int
    shape: str  # full encoded polyline for map display
