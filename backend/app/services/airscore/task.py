"""
Port of AirScore Task.pm — task distance calculations, remaining distance.

Geoff Wong's original Perl: https://github.com/geoffwong/airscore/blob/master/Task.pm
This is a 1:1 faithful port.
"""

from __future__ import annotations

import math

from .track_lib import (
    _acos_safe,
    cartesian2polar,
    ddequal,
    distance,
    plane_normal,
    polar2cartesian,
    qckdist2,
)

PI = math.pi

# Module-level caches (Task.pm line 26-30)
_wptdistcache: list[float] = []
_remainingdistcache: list[float] = []
_total_distance: float = 0.0
_goal_point: int = 0
_last_wpt_update: float = 0.0


# ---------- find_closest (Task.pm line 37-160) ----------

def find_closest(P1: dict, P2: dict, P3: dict) -> dict:
    """
    Simplified find_closest for dynamic re-optimisation during flight.
    P1 = current position, P2 = next waypoint (with radius), P3 = waypoint after.
    """
    C1 = polar2cartesian(P1)
    C2 = polar2cartesian(P2)
    C3 = polar2cartesian(P3)

    diff = C3 - C1
    denom = diff.dot(diff)
    if denom == 0:
        return P2

    u = (C2 - C1).dot(diff) / denom

    N = C1 + u * diff
    CL = N
    PR = cartesian2polar(CL)

    if 0 <= u <= 1 and distance(PR, P2) <= P2.get("radius", 0):
        # ~180-degree connect
        a = C1 - C2
        vl = a.length()
        if vl > 0:
            a = a / vl
        b = C3 - C2
        vl = b.length()
        if vl > 0:
            b = b / vl
        vn = a + b
        vl = vn.length()
        if vl > 0:
            vn = vn / vl
        O = vn * P2.get("radius", 0)
        CL = O + C2
    else:
        v = plane_normal(C1, C2)
        w = plane_normal(C3, C2)

        a = C1 - C2
        vla = a.length()
        if vla > 0:
            a = a / vla
        b = C3 - C2
        vlb = b.length()
        if vlb > 0:
            b = b / vlb

        O = a + b
        vl = O.length()
        if vl == 0:
            return P2

        dp = v.dot(w) / (v.length() * w.length()) if v.length() > 0 and w.length() > 0 else 1.0
        phi = _acos_safe(dp)
        phideg = phi * 180.0 / PI

        if phideg < 180:
            O = (P2.get("radius", 0) / vl) * O
        else:
            O = (-P2.get("radius", 0) / vl) * O

        CL = O + C2

    return cartesian2polar(CL)


# ---------- precompute_waypoint_dist (Task.pm line 162-333) ----------

def precompute_waypoint_dist(
    waypoints: list[dict], formula: dict
) -> tuple[int, int, int, float, float, float, float]:
    """
    Pre-compute cumulative and remaining distances for the task.
    Populates module-level caches.

    Each waypoint dict needs: 'lat', 'long' (radians), 'short_lat', 'short_long' (radians),
    'type' (start/speed/endspeed/goal/turnpoint), 'how' (entry/exit),
    'radius' (metres), 'shape' (circle/line).

    Returns: (spt, ept, gpt, ssdist, startssdist, endssdist, totdist)
    """
    global _wptdistcache, _remainingdistcache, _total_distance, _goal_point, _last_wpt_update

    wcount = len(waypoints)
    spt = 0
    ept = 0
    gpt = 0

    _goal_point = wcount - 1
    _last_wpt_update = 0.0

    for i in range(_goal_point + 1):
        wpt = waypoints[i]
        if wpt.get("type") in ("start", "speed"):
            spt = i
        if wpt.get("type") == "endspeed":
            ept = i
        if wpt.get("type") == "goal":
            gpt = i

    if ept == 0:
        ept = gpt

    # Error margin (Task.pm line 200-208)
    error_margin_pct = formula.get("errormargin", 0.05)
    for i in range(_goal_point + 1):
        errm = waypoints[i]["radius"] * error_margin_pct / 100.0
        if errm < 5.0:
            errm = 5.0
        waypoints[i]["margin"] = errm

    _wptdistcache = [0.0] * (wcount + 2)
    totdist = 0.0
    startssdist = 0.0
    endssdist = 0.0
    s1: dict = {}
    s2: dict = {}

    for i in range(_goal_point + 1):
        if s2:
            s1 = {"lat": s2["lat"], "long": s2["long"]}
        s2 = {"lat": waypoints[i]["short_lat"], "long": waypoints[i]["short_long"]}

        # Start SS dist (Task.pm line 229-236)
        if i == spt + 1:
            startssdist = totdist
            if startssdist < 1 and waypoints[i].get("how") == "exit":
                startssdist += waypoints[i]["radius"]

        # End SS dist (Task.pm line 239-248)
        if i == ept + 1:
            endssdist = totdist
            if waypoints[gpt].get("how") == "exit" and ddequal(waypoints[ept], waypoints[gpt]):
                endssdist += waypoints[gpt]["radius"]

        # Cumulative distance (Task.pm line 251-298)
        cdist = 0.0
        if i == 0:
            if waypoints[i].get("how") == "exit":
                cdist = waypoints[i]["radius"]
        elif i == 1:
            if waypoints[0].get("how") == "exit":
                cdist = distance(s1, s2) - waypoints[i - 1]["radius"]
            else:
                cdist = distance(s1, s2)
        elif ddequal(waypoints[i - 1], waypoints[i]):
            if waypoints[i].get("how") == "exit":
                cdist = waypoints[i]["radius"] - waypoints[i - 1]["radius"]
            else:
                if waypoints[i].get("shape") == "circle":
                    cdist = waypoints[i - 1]["radius"] - waypoints[i]["radius"]
                else:
                    cdist = waypoints[i - 1]["radius"]
        else:
            cdist = distance(s1, s2)

        totdist += cdist
        _wptdistcache[i + 1] = totdist

        # Check if pilot is inside waypoint (Task.pm line 303-311)
        sdist_q = qckdist2(s1, waypoints[i]) if s1 else 0
        waypoints[i]["inside"] = 1 if waypoints[i]["radius"] > sdist_q + 100 else 0

    _total_distance = totdist

    _remainingdistcache = [0.0] * (wcount + 2)
    for i in range(_goal_point + 1):
        _remainingdistcache[i] = totdist - _wptdistcache[i]
    _remainingdistcache[_goal_point + 1] = 0.0

    if endssdist == 0:
        endssdist = totdist
    ssdist = endssdist - startssdist

    return (spt, ept, gpt, ssdist, startssdist, endssdist, totdist)


# ---------- remaining_task_dist (Task.pm line 335-487) ----------

def remaining_task_dist(waypoints: list[dict], wmade: int, coord: dict) -> float:
    """
    Compute remaining distance to goal from pilot's current position.
    coord needs 'lat', 'long' (radians), optionally 'time'.
    """
    global _last_wpt_update

    nextwpt = waypoints[wmade]
    lastwpt = waypoints[wmade - 1] if wmade > 0 else nextwpt
    radius = 0.0

    # Concentric circles with goal exit (Task.pm line 349-371)
    if nextwpt.get("how") == "exit" and waypoints[_goal_point].get("how") == "exit":
        boob = True
        for wm in range(wmade, _goal_point + 1):
            if (waypoints[wm].get("lat") != waypoints[_goal_point].get("lat")
                    or waypoints[wm].get("long") != waypoints[_goal_point].get("long")):
                boob = False
                break
        if boob:
            s1 = {"lat": lastwpt["lat"], "long": lastwpt["long"]}
            cdist = qckdist2(coord, s1)
            return waypoints[_goal_point]["radius"] - cdist

    # Concentric circles with entry/exit/entry (Task.pm line 375-388)
    if (wmade < _goal_point
        and nextwpt.get("how") == "exit"
        and lastwpt.get("lat") == nextwpt.get("lat")
        and lastwpt.get("long") == nextwpt.get("long")
        and wmade + 1 < len(waypoints)
        and waypoints[wmade + 1].get("lat") == nextwpt.get("lat")
        and waypoints[wmade + 1].get("long") == nextwpt.get("long")
        and waypoints[wmade + 1].get("how") == "entry"):
        s1 = {"lat": lastwpt["lat"], "long": lastwpt["long"]}
        cdist = qckdist2(coord, s1)
        radius = waypoints[wmade]["radius"]
        remdist = _remainingdistcache[wmade + 1]
        return remdist + radius - cdist

    # Goal case (Task.pm line 390-417)
    if nextwpt.get("type") == "goal":
        remdist = _remainingdistcache[wmade]
        if (nextwpt.get("how") == "exit"
            and nextwpt.get("lat") == lastwpt.get("lat")
            and nextwpt.get("long") == lastwpt.get("long")):
            s1 = {"lat": lastwpt["lat"], "long": lastwpt["long"]}
            rdist = qckdist2(coord, s1)
            radius = nextwpt["radius"]
            return radius - rdist
        else:
            se = {"lat": nextwpt["lat"], "long": nextwpt["long"]}
            rdist = qckdist2(coord, se)
            if nextwpt.get("shape") != "line":
                radius = nextwpt["radius"]
                return rdist - radius
            return rdist

    # Normal case (Task.pm line 448-486)
    remdist = _remainingdistcache[wmade + 2] if wmade + 2 < len(_remainingdistcache) else 0.0

    coord_time = coord.get("time", 0)
    if coord_time - _last_wpt_update > 120:
        st = {"lat": waypoints[wmade + 1]["short_lat"], "long": waypoints[wmade + 1]["short_long"]}
        _last_wpt_update = coord_time
        nearwpt = find_closest(coord, nextwpt, st)
        nextwpt["short_lat"] = nearwpt["lat"]
        nextwpt["short_long"] = nearwpt["long"]

    s1 = {"lat": nextwpt["short_lat"], "long": nextwpt["short_long"]}
    s2 = {"lat": waypoints[wmade + 1]["short_lat"], "long": waypoints[wmade + 1]["short_long"]}
    rdist = qckdist2(coord, s1) + qckdist2(s1, s2)
    remdist = remdist + rdist - radius
    return remdist


# ---------- distance_flown (Task.pm line 587-599) ----------

def distance_flown(waypoints: list[dict], wmade: int, coord: dict) -> float:
    """Compute distance flown = total_distance - remaining_distance."""
    rem = remaining_task_dist(waypoints, wmade, coord)
    altdist = _total_distance - rem
    return max(altdist, 0.0)


# ---------- init_kmtime (Task.pm line 551-562) ----------

def init_kmtime(ssdist: float) -> list[int]:
    """Initialise per-km timing array for leading coefficient."""
    return [0] * (math.floor(ssdist / 1000.0) + 1)


# ---------- determine_utcmod (Task.pm line 564-582) ----------

def determine_utcmod(task: dict, coord: dict) -> int:
    """Handle UTC day-boundary correction."""
    coord_time = coord.get("time", 0)
    if coord_time > task.get("sfinish", 0):
        return 86400
    elif coord_time + 43200 < task.get("sstart", 0):
        return -86400
    return 0
