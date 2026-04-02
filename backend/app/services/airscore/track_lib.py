"""
Port of AirScore TrackLib.pm — geometry, distance, coordinate transforms.

Geoff Wong's original Perl: https://github.com/geoffwong/airscore/blob/master/TrackLib.pm
This is a 1:1 faithful port. Function names match the Perl originals.
"""

from __future__ import annotations

import math

# WGS-84 ellipsoid constants  (TrackLib.pm line 300-303)
_WGS84_A = 6378137.0
_WGS84_B = 6356752.3142
_WGS84_F = 1.0 / 298.257223563

PI = math.pi


# ---------- simple helpers (TrackLib.pm line 55-58) ----------

def round_val(number: float) -> int:
    """Perl-style rounding: int(number + 0.5)."""
    return int(number + 0.5)


def _acos_safe(x: float) -> float:
    """Safe acos that clamps input to [-1, 1].  (TrackLib.pm line 398-410)"""
    if x >= 1.0 or x <= -1.0:
        return 0.0
    return math.atan2(math.sqrt(1.0 - x * x), x)


# ---------- 3-D vector helpers ----------

class Vec3:
    """Minimal 3-D vector (replaces Perl Vector.pm)."""

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0):
        self.x = x
        self.y = y
        self.z = z

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec3:
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def __neg__(self) -> Vec3:
        return Vec3(-self.x, -self.y, -self.z)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Vec3):
            return NotImplemented
        return self.x == other.x and self.y == other.y and self.z == other.z

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def length(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def __repr__(self) -> str:
        return f"Vec3({self.x:.6f}, {self.y:.6f}, {self.z:.6f})"


# ---------- plane_normal (TrackLib.pm line 36-52) ----------

def plane_normal(c1: Vec3, c2: Vec3) -> Vec3:
    """Normal to the plane defined by two position vectors (cross product)."""
    return Vec3(
        c1.y * c2.z - c1.z * c2.y,
        c1.z * c2.x - c1.x * c2.z,
        c1.x * c2.y - c1.y * c2.x,
    )


# ---------- coordinate conversions (TrackLib.pm line 295-348) ----------

def polar2cartesian(p: dict) -> Vec3:
    """Convert polar (lat/long in radians) to WGS-84 cartesian."""
    sin_phi = math.sin(p["lat"])
    cos_phi = math.cos(p["lat"])
    sin_lam = math.sin(p["long"])
    cos_lam = math.cos(p["long"])
    H = 0.0
    e_sq = (_WGS84_A * _WGS84_A - _WGS84_B * _WGS84_B) / (_WGS84_A * _WGS84_A)
    nu = _WGS84_A / math.sqrt(1.0 - e_sq * sin_phi * sin_phi)
    return Vec3(
        (nu + H) * cos_phi * cos_lam,
        (nu + H) * cos_phi * sin_lam,
        ((1.0 - e_sq) * nu + H) * sin_phi,
    )


def cartesian2polar(c: Vec3) -> dict:
    """Convert WGS-84 cartesian back to polar (lat/long in radians, dlat/dlong in degrees)."""
    e_sq = (_WGS84_A * _WGS84_A - _WGS84_B * _WGS84_B) / (_WGS84_A * _WGS84_A)
    lon = math.atan2(c.y, c.x)
    lat = math.asin(
        math.sqrt(c.z * c.z / ((1.0 - e_sq) * _WGS84_A * (1.0 - e_sq) * _WGS84_A + c.z * c.z * e_sq))
    )
    if c.z < 0:
        lat = -lat
    return {
        "lat": lat,
        "long": lon,
        "dlat": lat * 180.0 / PI,
        "dlong": lon * 180.0 / PI,
    }


# ---------- ddequal (TrackLib.pm line 352-364) ----------

def ddequal(wp1: dict, wp2: dict) -> bool:
    """Check if two waypoints share the same location (degree coords)."""
    return wp1.get("dlat") == wp2.get("dlat") and wp1.get("dlong") == wp2.get("dlong")


# ---------- Vincenty inverse distance (TrackLib.pm line 460-545) ----------

def distance(p1: dict, p2: dict) -> float:
    """
    Vincenty inverse formula for ellipsoids.
    Inputs: dicts with 'lat' and 'long' keys in RADIANS.
    Returns: distance in metres.
    """
    a = _WGS84_A
    b = _WGS84_B
    f = _WGS84_F

    L = p2["long"] - p1["long"]
    U1 = math.atan((1.0 - f) * math.tan(p1["lat"]))
    U2 = math.atan((1.0 - f) * math.tan(p2["lat"]))
    sin_U1 = math.sin(U1)
    cos_U1 = math.cos(U1)
    sin_U2 = math.sin(U2)
    cos_U2 = math.cos(U2)

    lam = L
    lam_prev = 2.0 * PI
    iter_limit = 20

    cos_sq_alpha = 0.0
    sin_sigma = 0.0
    cos_sigma = 0.0
    sigma = 0.0
    cos_2sigma_m = 0.0

    while abs(lam - lam_prev) > 1e-12 and iter_limit > 0:
        iter_limit -= 1
        sin_lam = math.sin(lam)
        cos_lam = math.cos(lam)
        sin_sigma = math.sqrt(
            (cos_U2 * sin_lam) ** 2
            + (cos_U1 * sin_U2 - sin_U1 * cos_U2 * cos_lam) ** 2
        )
        if sin_sigma == 0.0:
            return 0.0  # co-incident points
        cos_sigma = sin_U1 * sin_U2 + cos_U1 * cos_U2 * cos_lam
        sigma = math.atan2(sin_sigma, cos_sigma)
        sin_alpha = cos_U1 * cos_U2 * sin_lam / sin_sigma
        cos_sq_alpha = 1.0 - sin_alpha * sin_alpha
        if cos_sq_alpha == 0.0:
            cos_2sigma_m = 0.0
        else:
            cos_2sigma_m = cos_sigma - 2.0 * sin_U1 * sin_U2 / cos_sq_alpha
        C = f / 16.0 * cos_sq_alpha * (4.0 + f * (4.0 - 3.0 * cos_sq_alpha))
        lam_prev = lam
        lam = L + (1.0 - C) * f * sin_alpha * (
            sigma
            + C * sin_sigma * (cos_2sigma_m + C * cos_sigma * (-1.0 + 2.0 * cos_2sigma_m * cos_2sigma_m))
        )

    if iter_limit == 0:
        return 0.0  # failed to converge

    u_sq = cos_sq_alpha * (a * a - b * b) / (b * b)
    A_coeff = 1.0 + u_sq / 16384.0 * (4096.0 + u_sq * (-768.0 + u_sq * (320.0 - 175.0 * u_sq)))
    B_coeff = u_sq / 1024.0 * (256.0 + u_sq * (-128.0 + u_sq * (74.0 - 47.0 * u_sq)))
    delta_sigma = B_coeff * sin_sigma * (
        cos_2sigma_m
        + B_coeff / 4.0 * (
            cos_sigma * (-1.0 + 2.0 * cos_2sigma_m * cos_2sigma_m)
            - B_coeff / 6.0 * cos_2sigma_m * (-3.0 + 4.0 * sin_sigma * sin_sigma)
            * (-3.0 + 4.0 * cos_2sigma_m * cos_2sigma_m)
        )
    )
    return b * A_coeff * (sigma - delta_sigma)


# ---------- qckdist2 (TrackLib.pm line 553-565) ----------

def qckdist2(p1: dict, p2: dict) -> float:
    """
    Quick approximate distance in metres.
    Inputs: dicts with 'lat' and 'long' in RADIANS.
    Good for small distances and sorting.
    """
    x = p2["lat"] - p1["lat"]
    y = (p2["long"] - p1["long"]) * math.cos((p1["lat"] + p2["lat"]) / 2.0)
    return 6371009.0 * math.sqrt(x * x + y * y)


# ---------- degree-based convenience wrappers ----------

def distance_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Vincenty distance from degree-based coordinates. Returns metres."""
    r = PI / 180.0
    return distance({"lat": lat1 * r, "long": lon1 * r}, {"lat": lat2 * r, "long": lon2 * r})


def to_rad_dict(dlat: float, dlong: float, **extra) -> dict:
    """Build a waypoint dict with both radian and degree fields from degrees."""
    r = PI / 180.0
    d = {"lat": dlat * r, "long": dlong * r, "dlat": dlat, "dlong": dlong}
    d.update(extra)
    return d
