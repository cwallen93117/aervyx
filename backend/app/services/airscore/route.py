"""
Port of AirScore Route.pm — shortest route through cylinders.

Geoff Wong's original Perl: https://github.com/geoffwong/airscore/blob/master/Route.pm
This is a 1:1 faithful port.
"""

from __future__ import annotations

import math

from .track_lib import (
    Vec3,
    _acos_safe,
    cartesian2polar,
    ddequal,
    distance,
    plane_normal,
    polar2cartesian,
    qckdist2,
)

PI = math.pi


# ---------- sllequal (Route.pm line 80-91) ----------

def sllequal(wp1: dict, wp2: dict) -> bool:
    """Check if two waypoints' short positions are at the same location."""
    return (
        abs(wp1.get("short_lat", 0) - wp2.get("short_lat", 0)) < 0.0000001
        and abs(wp1.get("short_long", 0) - wp2.get("short_long", 0)) < 0.0000001
    )


# ---------- find_closest (Route.pm line 99-380) ----------

def find_closest(
    P1: dict,
    P2: dict | None,
    P3: dict | None,
    O2: dict | None = None,
    dirn: dict | None = None,
) -> dict:
    """
    Given three waypoints P1->P2->P3, find the optimal point on P2's cylinder
    that minimises the total route distance P1->P2'->P3.

    Returns a polar dict with 'lat', 'long', 'dlat', 'dlong'.
    """
    C1 = polar2cartesian(P1)
    C2 = polar2cartesian(P2) if P2 is not None else None

    # --- P2 is None: straight-through case (Route.pm line 113-147) ---
    if P2 is None or C2 is None:
        C3 = polar2cartesian(P3) if P3 is not None else Vec3()
        O = C1 - C3
        vl = O.length()
        if vl < 0.01:
            if dirn is not None:
                D1 = polar2cartesian(dirn)
                O = D1 - C1
            else:
                O = Vec3(1000, 1000, 1000)
            vl = O.length()
        radius = (O2 or P2 or {}).get("radius", 0)
        O = (radius / vl) * O
        CL = O + C3
        return cartesian2polar(CL)

    # --- Line shape (Route.pm line 149-153) ---
    if P2.get("shape") == "line":
        return P2

    if O2 is None:
        O2 = P2

    # --- P3 is None: end-of-line case (Route.pm line 160-198) ---
    if P3 is None:
        O = C1 - C2
        vl = O.length()
        if vl > 0.01:
            O = (P2["radius"] / vl) * O
            CL = O + C2
        else:
            if dirn is not None:
                D1 = polar2cartesian(dirn)
                O = D1 - C1
                vl = O.length()
                O = (O2["radius"] / vl) * O
                CL = O + C2
            else:
                return P2
        return cartesian2polar(CL)

    C3 = polar2cartesian(P3)

    # --- Same centre C1 == C3 (Route.pm line 215-237) ---
    if C1 == C3:
        O = C2 - C1
        vl = O.length()
        if vl < 0.01:
            return P2
        O = (P2["radius"] / vl) * O
        CL = C2 - O
        return cartesian2polar(CL)

    # --- Same centre C1 == C2 (Route.pm line 241-255) ---
    T = C1 - C2
    if T.length() < 0.01:
        O = C3 - C2
        vl = O.length()
        if vl > 0:
            O = (P2["radius"] / vl) * O
        CL = C2 + O
        return cartesian2polar(CL)

    # --- General case: project C2 onto line C1->C3 (Route.pm line 257-323) ---
    diff = C3 - C1
    denom = diff.dot(diff)
    if denom == 0:
        return P2
    u = (C2 - C1).dot(diff) / denom

    N = C1 + u * diff
    CL = N
    PR = cartesian2polar(CL)

    if 0 <= u <= 1 and distance(PR, P2) <= P2["radius"]:
        # 180-degree connect case
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
        O = vn * P2["radius"]
        CL = O + C2
    else:
        # Normal angle-bisector case (Route.pm line 324-367)
        v = plane_normal(C1, C2)
        w = plane_normal(C3, C2)
        dp = v.dot(w) / (v.length() * w.length()) if v.length() > 0 and w.length() > 0 else 1.0
        phi = _acos_safe(dp)
        phideg = phi * 180.0 / PI

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

        if phideg < 180:
            O = (P2["radius"] / vl) * O
        else:
            O = (-P2["radius"] / vl) * O

        CL = O + C2

    return cartesian2polar(CL)


def _qckdist3(P1: dict, P2: dict, P3: dict) -> float:
    """Quick 3-point route distance (Route.pm line 382-390)."""
    return qckdist2(P1, P2) + qckdist2(P2, P3)


# ---------- iterate_short_route (Route.pm line 392-442) ----------

def iterate_short_route(orig: list[dict], wpts: list[dict]) -> list[dict]:
    """One iteration of shortest-route refinement."""
    num = len(wpts)
    result = [wpts[0]]
    newcl = wpts[0]

    for i in range(num - 2):
        newcl = find_closest(newcl, orig[i + 1], wpts[i + 2])
        if _qckdist3(wpts[i], newcl, wpts[i + 2]) < _qckdist3(wpts[i], wpts[i + 1], wpts[i + 2]):
            result.append(newcl)
        else:
            result.append(wpts[i + 1])

    result.append(wpts[num - 1])
    return result


# ---------- find_shortest_route (Route.pm line 449-551) ----------

def find_shortest_route(waypoints: list[dict]) -> list[dict]:
    """
    Compute the shortest route through all waypoint cylinders.
    Each waypoint dict needs: 'lat', 'long' (radians), 'radius' (metres),
    'dlat', 'dlong' (degrees), optionally 'shape', 'how', 'name'.
    Returns list of optimised polar dicts.
    """
    num = len(waypoints)
    if num < 1:
        return []
    if num == 1:
        first = cartesian2polar(polar2cartesian(waypoints[0]))
        return [first]

    # First pass (Route.pm line 480-539)
    it1 = [waypoints[0]]
    newcl = waypoints[0]

    for i in range(num - 2):
        if ddequal(waypoints[i + 1], waypoints[i + 2]):
            j = i + 2
            while j < num - 1 and ddequal(newcl, waypoints[j]):
                j += 1
            if j == num - 1:
                newcl = find_closest(newcl, None, waypoints[j - 1], waypoints[j - 1])
            else:
                dirn = waypoints[j]
                newcl = find_closest(newcl, waypoints[i + 1], None, None, dirn)
        else:
            newcl = find_closest(newcl, waypoints[i + 1], waypoints[i + 2])
        it1.append(newcl)

    # End point
    newcl = find_closest(newcl, waypoints[num - 1], None)
    it1.append(newcl)

    # Iterate refinement (Route.pm line 545-547)
    it2 = iterate_short_route(waypoints, it1)
    it3 = iterate_short_route(waypoints, it2)
    return it3


# ---------- short_dist (Route.pm line 622-635) ----------

def short_dist(w1: dict, w2: dict) -> float:
    """Distance between two waypoints' short-route positions."""
    s1 = {"lat": w1["short_lat"], "long": w1["short_long"]}
    s2 = {"lat": w2["short_lat"], "long": w2["short_long"]}
    return distance(s1, s2)


# ---------- task_distance (Route.pm line 648-763) ----------

def task_distance(waypoints: list[dict]) -> tuple:
    """
    Compute task distance using the shortest-route waypoints.
    Each waypoint needs 'short_lat', 'short_long' (radians), 'type', 'how',
    'radius' (metres), 'shape'.

    Returns: (spt, ept, gpt, ssdist, startssdist, endssdist, totdist)
    """
    allpoints = len(waypoints)
    spt = 0
    ept = 0
    gpt = 0

    for i in range(allpoints):
        wpt = waypoints[i]
        if wpt.get("type") in ("start", "speed"):
            spt = i
        if wpt.get("type") == "endspeed":
            ept = i
        if wpt.get("type") == "goal":
            gpt = i

    if gpt == 0:
        gpt = allpoints - 1
    if ept == 0:
        ept = gpt

    cwdist = 0.0
    startssdist = 0.0
    endssdist = 0.0

    for i in range(allpoints):
        # Start SS dist  (Route.pm line 704-710)
        if i == spt:
            startssdist = cwdist
            if startssdist < 1 and waypoints[i].get("how") == "exit":
                startssdist += waypoints[i]["radius"]

        # End SS dist  (Route.pm line 714-728)
        if i == ept:
            endssdist = cwdist
            if ept == gpt and waypoints[gpt].get("how") == "exit":
                endssdist += waypoints[gpt]["radius"]

        if i < allpoints - 1:
            if ddequal(waypoints[i], waypoints[i + 1]) and waypoints[i + 1].get("how") == "exit":
                cwdist += waypoints[i + 1]["radius"]
                if waypoints[i].get("type") != "start":
                    cwdist -= waypoints[i]["radius"]
            else:
                sdist = short_dist(waypoints[i], waypoints[i + 1])
                if (
                    (i + 1 != gpt)
                    or (i + 1 == gpt and ept == gpt)
                    or (i + 1 == gpt and waypoints[gpt].get("shape") != "circle")
                ):
                    cwdist += sdist
                elif (
                    i + 1 == gpt
                    and waypoints[gpt].get("shape") == "circle"
                    and ddequal(waypoints[i], waypoints[i + 1])
                    and waypoints[i + 1].get("how") == "entry"
                ):
                    cwdist += waypoints[i]["radius"] - waypoints[i + 1]["radius"]

    ssdist = endssdist - startssdist
    return (spt, ept, gpt, ssdist, startssdist, endssdist, cwdist)


# ---------- in_semicircle (Route.pm line 765-792) ----------

def in_semicircle(waypoints: list[dict], wmade: int, coord: dict) -> bool:
    """
    Check if coord is in the correct semicircle of waypoints[wmade].
    coord needs a 'cart' key (Vec3).
    """
    wpt = waypoints[wmade]
    prev = wmade - 1
    while prev > 0 and ddequal(wpt, waypoints[prev]):
        prev -= 1

    c = polar2cartesian(wpt)
    p = polar2cartesian(waypoints[prev])

    bvec = c - p
    pvec = coord["cart"] - c
    return bvec.dot(pvec) > 0
