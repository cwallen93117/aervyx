"""
Port of AirScore Gap.pm — core GAP scoring formula.

Geoff Wong's original Perl: https://github.com/geoffwong/airscore/blob/master/Gap.pm
This is a 1:1 faithful port. Function names and logic match the Perl originals.
All line references are to the master-branch Gap.pm.
"""

from __future__ import annotations

import math


# ---------- helpers (Gap.pm line 32-78) ----------

def _round(number: float) -> int:
    return int(number + 0.5)


def _min_list(lst: list[float]) -> float:
    return min(lst) if lst else 0.0


def _max_list(lst: list[float]) -> float:
    return max(lst) if lst else 0.0


def _spread(buc: list[float]) -> list[float]:
    """Smooth a difficulty bucket array (Gap.pm line 62-78)."""
    sz = len(buc) - 1
    nbuc = [0.0] * len(buc)
    nbuc[0] = float(buc[0])
    for j in range(1, sz + 1):
        nbuc[j - 1] += buc[j] / 3.0
        nbuc[j] += buc[j] * 2.0 / 3.0
    return nbuc


# ---------- select_coeff (Gap.pm line 81-93) ----------

def select_coeff(formula: dict) -> str:
    """Determine which leading coefficient field to use."""
    fclass = formula.get("class", "gap")
    version = int(formula.get("version", 0))
    if fclass in ("pwc", "gap", "ozgap", "ggap") and version > 2022:
        return "tarLeadingCoeff2"
    return "tarLeadingCoeff"


# ---------- day_quality (Gap.pm line 345-459) ----------

def day_quality(
    taskt: dict, formula: dict
) -> tuple[float, float, float, float]:
    """
    Calculate task validity — distance, time, launch, stopped.
    Returns: (distance_validity, time_validity, launch_validity, stopped_validity)
    """
    if taskt["pilots"] == 0:
        return (0.0, 0.1, 0.0, 1.0)

    # Launch validity (Gap.pm line 363-377)
    x_launch = taskt["launched"] / (taskt["pilots"] * formula["nomlaunch"])
    launch = 0.027 * x_launch + 2.917 * x_launch * x_launch - 1.944 * x_launch ** 3
    if x_launch > 1 or launch > 1:
        launch = 1.0
    if launch < 0:
        launch = 0.0
    if taskt.get("launchvalid", 1) == 0:
        launch = 0.0

    # Distance validity (Gap.pm line 380-403)
    if formula.get("distmeasure") == "median":
        dist_val = taskt.get("median", 0) / formula["nomdist"]
    else:
        mdist = (formula.get("nomgoal", 20) / 100.0) * (taskt["maxdist"] - formula["nomdist"])
        if mdist < 0:
            mdist = 0
        nomdistarea = taskt["launched"] * (
            (1.0 + formula.get("nomgoal", 20) / 100.0) * (formula["nomdist"] - formula["mindist"]) + mdist
        ) / 2.0
        if nomdistarea == 0:
            dist_val = 0.0
        else:
            dist_val = (taskt["distance"] - taskt["launched"] * formula["mindist"]) / nomdistarea

    dist_val = max(0.0, min(1.0, dist_val))

    # Time validity (Gap.pm line 405-434)
    # GAP2021+ uses fastest time; older versions use 2nd-fastest (tqtime)
    if taskt["ess"] > 0:
        version = int(formula.get("version", 0))
        if version >= 2021:
            tmin = taskt["fastest"]
        else:
            tmin = taskt.get("tqtime", taskt["fastest"])
        x_time = tmin / formula["nomtime"]
    else:
        x_time = taskt["maxdist"] / formula["nomdist"]

    if x_time < 1:
        time_val = -0.271 + 2.912 * x_time - 2.098 * x_time ** 2 + 0.457 * x_time ** 3
    else:
        time_val = 1.0
    time_val = max(0.1, min(1.0, time_val))

    # Stopped validity (Gap.pm line 436-458)
    if taskt.get("stopped", 0) > 0:
        if taskt["maxdist"] >= taskt.get("endssdistance", 0):
            stopped = 1.0
        else:
            denom = taskt.get("endssdistance", 0) - taskt["maxdist"] + 1
            if denom <= 0:
                stopped = 1.0
            else:
                inner = (taskt["maxdist"] - taskt.get("avdist", 0)) / denom
                inner *= math.sqrt(taskt.get("stddev", 0) / 5000.0)
                stopped = math.sqrt(max(inner, 0.0)) + (taskt.get("landed", 0) / max(taskt["launched"], 1)) ** 3
        stopped = min(1.0, stopped)
    else:
        stopped = 1.0

    return (dist_val, time_val, launch, stopped)


# ---------- points_weight (Gap.pm line 463-526) ----------

def points_weight(
    task: dict, taskt: dict, formula: dict
) -> tuple[float, float, float, float]:
    """
    Determine available points for distance, speed, start/leading, arrival.
    Returns: (Adistance, Aspeed, Astart, Aarrival)
    """
    quality = taskt["quality"]
    launched = taskt["launched"]
    if launched == 0:
        return (0.0, 0.0, 0.0, 0.0)
    x = taskt["goal"] / launched

    # Distance weight (Gap.pm line 477-484)
    if formula.get("weightdist") == "post2014":
        distweight = 0.9 - 1.665 * x + 1.713 * x ** 2 - 0.587 * x ** 3
    else:
        distweight = 1.0 - 0.8 * math.sqrt(x)

    Adistance = 1000.0 * quality * distweight

    # GAP2021+ leading weight: leading_weight_factor overrides the legacy
    # weightstart (0.175) as the fraction of non-distance points for leading.
    # E.g. 0.26 for GAP2023 PG.  Speed gets whatever remains after
    # distance, leading, and arrival.
    lwf = formula.get("leading_weight_factor", 1.0)
    if lwf != 1.0 and lwf > 0:
        non_dist = 1000.0 * quality * (1.0 - distweight)
        Astart = non_dist * lwf
        Aarrival = non_dist * formula.get("weightarrival", 0.125)

        if task.get("class") == "HG":
            Aarrival = non_dist * 1.0 / 8.0

        if task.get("arrival") == "off":
            Aarrival = 0.0
        if task.get("departure") == "off":
            Astart = 0.0

        Aspeed = non_dist - Astart - Aarrival
    else:
        # Legacy AirScore relative allocation
        Astart = 1000.0 * quality * (1.0 - distweight) * formula.get("weightstart", 0.175)
        Aarrival = 1000.0 * quality * (1.0 - distweight) * formula.get("weightarrival", 0.125)
        speedweight = formula.get("weightspeed", 0.7)

        # Hang glider override (Gap.pm line 493-500)
        if task.get("class") == "HG":
            Adistance = 1000.0 * (0.9 - 1.665 * x + 1.713 * x ** 2 - 0.587 * x ** 3) * quality
            Astart = 1000.0 * quality * (1.0 - distweight) * 1.4 / 8.0
            Aarrival = 1000.0 * quality * (1.0 - distweight) * 1.0 / 8.0

        # Arrival off (Gap.pm line 502-506)
        if task.get("arrival") == "off":
            Aarrival = 0.0
            speedweight += formula.get("weightarrival", 0.125)

        # Departure off (Gap.pm line 508-512)
        if task.get("departure") == "off":
            Astart = 0.0
            speedweight += formula.get("weightstart", 0.175)

        Aspeed = 1000.0 * quality * (1.0 - distweight) * speedweight

    # Scale to validity (Gap.pm line 515-522)
    if formula.get("scaletovalidity"):
        dem = Adistance + Aspeed + Aarrival + Astart
        if dem > 0:
            Adistance = 1000.0 * quality * Adistance / dem
            Aspeed = 1000.0 * quality * Aspeed / dem
            Aarrival = 1000.0 * quality * Aarrival / dem
            Astart = 1000.0 * quality * Astart / dem

    return (Adistance, Aspeed, Astart, Aarrival)


# ---------- calc_kmdiff (Gap.pm line 529-597) ----------

def calc_kmdiff(task: dict, taskt: dict, formula: dict) -> list[float]:
    """
    Build the cumulative distance-difficulty curve.
    Returns a list indexed by 100m buckets.
    """
    maxdist = taskt["maxdist"]
    launched = taskt["launched"]
    goal = taskt["goal"]
    Nlo = launched - goal
    distspread = taskt.get("distspread", [])
    lookahead = taskt.get("lookahead", 30)

    num_buckets = max(math.floor(maxdist / 100.0) + 1, 1)
    kmdiff = [0.0] * num_buckets

    difsum = 0.0
    for ref in distspread:
        difdist = int(ref["Distance"]) - int(lookahead)
        if difdist < 0:
            difdist = 0
        if difdist < num_buckets:
            kmdiff[difdist] += ref["Difficulty"]
        difsum += ref["Difficulty"]

    # Cumulative (Gap.pm line 574-593)
    x = 0.0
    for dif in range(len(kmdiff)):
        x += kmdiff[dif]
        if formula.get("diffcalc") == "lo" and difsum > 0:
            kmdiff[dif] = x / difsum
        else:
            kmdiff[dif] = x / max(launched, 1)

    return kmdiff


# ---------- pilot_speed (Gap.pm line 755-799) ----------

def pilot_speed(
    formula: dict, task: dict, taskt: dict, pil: dict, Aspeed: float
) -> float:
    """Calculate pilot speed score."""
    Tmin = taskt["fastest"]
    Ptime = pil.get("time", 0)
    if Ptime <= 0:
        return 0.0

    # Gap.pm line 773-780
    if formula.get("speedcalc") == "extended":
        Pspeed = Aspeed * (1.0 - ((Ptime - Tmin) / 3600.0 / math.sqrt(Tmin / 1800.0)) ** (2.0 / 3.0))
    else:
        Pspeed = Aspeed * (1.0 - ((Ptime - Tmin) / 3600.0 / math.sqrt(Tmin / 3600.0)) ** (5.0 / 6.0))

    if Pspeed < 0:
        Pspeed = 0.0

    # NaN check (Gap.pm line 792-796)
    if math.isnan(Pspeed):
        Pspeed = 0.0

    return Pspeed


# ---------- pilot_distance (Gap.pm line 801-814) ----------

def pilot_distance(
    formula: dict, task: dict, taskt: dict, pil: dict, Adistance: float
) -> float:
    """Calculate pilot distance score with linear + difficulty components."""
    kmdiff = calc_kmdiff(task, taskt, formula)
    maxdist = taskt["maxdist"]
    pildist = pil["distance"]
    lineardist = formula.get("lineardist", 0.5)

    bucket = math.floor(pildist / 100.0)
    bucket = min(bucket, len(kmdiff) - 1)

    Pdist = Adistance * (
        (pildist / maxdist) * lineardist
        + kmdiff[bucket] * (1.0 - lineardist)
    )
    return Pdist


# ---------- pilot_arrival (Gap.pm line 601-641) ----------

def pilot_arrival(
    formula: dict, task: dict, taskt: dict, pil: dict, Aarrival: float
) -> float:
    """Calculate pilot arrival score (timed or place)."""
    if pil.get("time", 0) <= 0:
        return 0.0

    if formula.get("arrival") == "timed":
        # OzGAP / Timed arrival (Gap.pm line 612-615)
        x = 1.0 - pil.get("timeafter", 0) / (90.0 * 60.0)
        Parrival = Aarrival * (0.2 + 0.037 * x + 0.13 * x ** 2 + 0.633 * x ** 3)
    else:
        # Place arrival (Gap.pm line 619-628)
        if taskt["ess"] > 0:
            x = 1.0 - (pil.get("place", 1) - 1) / taskt["ess"]
            Parrival = Aarrival * (0.2 + 0.037 * x + 0.13 * x ** 2 + 0.633 * x ** 3)
        else:
            return 0.0

    return max(Parrival, 0.0)


# ---------- pilot_departure_leadout (Gap.pm line 644-753) ----------

def pilot_departure_leadout(
    formula: dict, task: dict, taskt: dict, pil: dict,
    Astart: float, Aspeed: float,
) -> float:
    """Calculate pilot departure / leadout score."""
    Cmin = taskt.get("mincoeff", 0)
    Pdepart = 0.0

    departure_mode = task.get("departure", "off")

    if departure_mode == "leadout":
        # Leading coefficient (Gap.pm line 655-673)
        coeff = pil.get("coeff", 0)
        if coeff > 0:
            if coeff <= Cmin:
                Pdepart = Astart
            elif Cmin <= 0:
                Pdepart = 0.0
            else:
                Pdepart = Astart * (1.0 - ((coeff - Cmin) / math.sqrt(Cmin)) ** (2.0 / 3.0))

    elif departure_mode == "kmbonus":
        # KM bonus (Gap.pm line 675-718)
        kmarr = taskt.get("kmmarker", [])
        if kmarr:
            notkm = task.get("ssdistance", 0) * 0.15
            if notkm < 10000.0:
                notkm = 10000.0
            kmdist = math.floor((task.get("ssdistance", 0) - notkm) / 1000.0)
            for km in range(1, int(kmdist)):
                if km < len(pil.get("kmmarker", [])) and km < len(kmarr):
                    if pil["kmmarker"][km] > 0 and kmarr[km] > 0:
                        x = 1.0 - (pil["kmmarker"][km] - kmarr[km]) / 600.0
                        if x > 0:
                            Pdepart += 0.2 + 0.037 * x + 0.13 * x ** 2 + 0.633 * x ** 3
            Pdepart = Pdepart * Astart * 1.25 / max(kmdist, 1)
            Pdepart = min(Pdepart, Astart)
        else:
            Pdepart = 0.0

    elif departure_mode == "off":
        Pdepart = 0.0

    else:
        # Normal departure points (Gap.pm line 726-735)
        firstdepart = taskt.get("firstdepart", 0)
        nomtime = formula.get("nomtime", 3600)
        x = (pil.get("startSS", 0) - firstdepart) / nomtime
        if x < 0.5 and pil.get("time", 0) > 0:
            Pspeed = pilot_speed(formula, task, taskt, pil, Aspeed)
            Pdepart = Pspeed * Astart / max(Aspeed, 0.001) * (
                1.0 - 6.312 * x + 10.932 * x ** 2 - 2.990 * x ** 3
            )

    # Sanity (Gap.pm line 740-751)
    if math.isnan(Pdepart):
        Pdepart = 0.0
    return max(Pdepart, 0.0)


# ---------- missing_leading_area (Gap.pm line 858-880) ----------

def missing_leading_area(
    task: dict, remainingss: float, timedif: float, lctype: str
) -> float:
    """Compute missing leading area for pilots who didn't make ESS."""
    ssdistance = task.get("ssdistance", 1)
    if ssdistance == 0:
        return 0.0

    if lctype == "tarLeadingCoeff":
        return timedif * remainingss / 1800.0 / ssdistance

    if task.get("class") == "HG":
        return timedif * remainingss * remainingss / 1800.0 / ssdistance
    else:
        falling = (1.0 - 10.0 ** (-3.0 * remainingss / ssdistance)) ** 2
        return falling * timedif * remainingss / 1800.0 / ssdistance


# ---------- points_allocation (Gap.pm line 1055-1147) ----------

def points_allocation(
    task: dict, taskt: dict, formula: dict, pilots: list[dict]
) -> list[dict]:
    """
    Main scoring entry point. Allocates GAP points to all pilots.

    task: task-level config (class, departure, arrival, sstopped, etc.)
    taskt: task totals from task_totals()
    formula: formula parameters
    pilots: list of pilot dicts from ordered_results()

    Each pilot dict must have:
        distance, time, place, goal, result, penalty, coeff, startSS, endSS,
        timeafter, stopalt, stoptime, kmmarker (optional)

    Returns the same pilot list with added scoring fields:
        Pdist, Pspeed, Parrival, Pdepart, Pscore
    """
    quality = taskt["quality"]
    leadingcoeff_field = select_coeff(formula)

    # Available points (Gap.pm line 1073)
    Adistance, Aspeed, Astart, Aarrival = points_weight(task, taskt, formula)

    # Adjust leading coefficients for pilots who didn't make ESS (Gap.pm line 949-988)
    if taskt.get("goal", 0) > 0:
        for pil in pilots:
            if (pil.get("endSS", 0) - pil.get("startSS", 0)) < 1 and pil.get("startSS", 0) > 0:
                if taskt.get("lastarrival", 0) > 0:
                    remdist = task.get("endssdistance", 0) - pil.get("distance", 0)
                    tasktime = task.get("sfinish", 0) - task.get("sstart", 0)
                    timedif = taskt.get("lastarrival", 0) - task.get("sstart", 0)

                    submaxlc = missing_leading_area(task, remdist, tasktime, leadingcoeff_field)
                    addlastlc = missing_leading_area(task, remdist, timedif, leadingcoeff_field)
                    pil["coeff"] = pil.get("coeff", 0) - submaxlc + addlastlc

                    if pil["coeff"] < 0:
                        pil["coeff"] = 0

                    if pil["coeff"] > 0 and pil["coeff"] < taskt.get("mincoeff", float("inf")):
                        taskt["mincoeff"] = pil["coeff"]

    # Score each pilot (Gap.pm line 1076-1146)
    for pil in pilots:
        penalty = pil.get("penalty", 0)

        # Distance (Gap.pm line 1085)
        Pdist = pilot_distance(formula, task, taskt, pil, Adistance)

        # Speed (Gap.pm line 1088)
        Pspeed = pilot_speed(formula, task, taskt, pil, Aspeed)

        # Departure/leading (Gap.pm line 1091)
        Pdepart = pilot_departure_leadout(formula, task, taskt, pil, Astart, Aspeed)

        # Arrival (Gap.pm line 1094)
        Parrival = pilot_arrival(formula, task, taskt, pil, Aarrival)

        # Penalty for not making goal (Gap.pm line 1097-1114)
        if pil.get("goal", 0) == 0:
            sspenalty = formula.get("sspenalty", 1.0)
            if task.get("sstopped", 0) == 0:
                Pspeed -= Pspeed * sspenalty
                Parrival -= Parrival * sspenalty
            else:
                if pil.get("stoptime", 0) == 0:
                    Pspeed -= Pspeed * sspenalty
                    Parrival -= Parrival * sspenalty

        # DNF/Absent sanity (Gap.pm line 1118-1124)
        if pil.get("result") in ("dnf", "abs"):
            Pdist = 0.0
            Pspeed = 0.0
            Parrival = 0.0
            Pdepart = 0.0

        # Total (Gap.pm line 1130-1134)
        Pscore = Pdist + Pspeed + Parrival + Pdepart - penalty
        if Pscore < 0:
            Pscore = 0.0

        pil["Pdist"] = Pdist
        pil["Pspeed"] = Pspeed
        pil["Parrival"] = Parrival
        pil["Pdepart"] = Pdepart
        pil["Pscore"] = Pscore

    return pilots


# ---------- task_totals (Gap.pm line 102-337) ----------
# This is a DB-free version. The caller must aggregate stats and pass them in.

def build_task_totals(
    formula: dict,
    task: dict,
    pilot_results: list[dict],
) -> dict:
    """
    Build the taskt dict from pilot results (no DB queries).

    Each pilot_result dict should have:
        distance (metres), time (seconds), goal (0/1), result (str),
        startSS (epoch), endSS (epoch), coeff (leading coeff), stopalt, stoptime

    formula needs: mindist, nomtime, nomdist, nomlaunch, nomgoal,
        glidebonus, diffdist, difframp, diffcalc

    task needs: stopped/sstopped, endssdistance, ssdistance, launchvalid, sstart, sfinish

    Returns the taskt dict ready for day_quality() and points_weight().
    """
    mindist = formula.get("mindist", 5000)
    glidebonus = formula.get("glidebonus", 0) if task.get("sstopped", 0) > 0 else 0

    # Filter out absent pilots (Gap.pm line 132)
    active = [p for p in pilot_results if p.get("result") != "abs"]

    pilots_total = len(active)
    launched = sum(1 for p in active if p.get("distance", 0) > 0 or p.get("result") == "lo")
    landed = 0
    if task.get("sstopped", 0) > 0:
        landed = sum(
            1 for p in active
            if (p.get("stopalt", 0) == 0 and (p.get("distance", 0) > 0 or p.get("result") == "lo"))
            or p.get("goal", 0) > 0
        )

    # Effective distances (respecting mindist floor)
    eff_distances = []
    for p in active:
        d = p.get("distance", 0)
        if d < mindist and (d > 0 or p.get("result") == "lo"):
            d = mindist
        # Glide bonus for stopped tasks (Gap.pm line 912-923)
        if glidebonus > 0 and p.get("stopalt", 0) > 0:
            goal_alt = task.get("goalalt", 0)
            if p["stopalt"] > goal_alt:
                d += glidebonus * (p["stopalt"] - goal_alt)
                ssdist = task.get("ssdistance", 0)
                if ssdist > 0 and d > ssdist:
                    d = ssdist
        eff_distances.append(d)

    totdist = sum(max(d, mindist) if d > 0 else 0 for d in eff_distances)
    maxdist = max(eff_distances) if eff_distances else mindist
    if maxdist < mindist:
        maxdist = mindist

    goal = sum(1 for p in active if p.get("goal", 0) > 0)
    ess = sum(1 for p in active if (p.get("endSS", 0) - p.get("startSS", 0)) > 0)

    # Fastest / 2nd fastest (Gap.pm line 175-189)
    times = sorted(
        [p.get("endSS", 0) - p.get("startSS", 0) for p in active if (p.get("endSS", 0) - p.get("startSS", 0)) > 0]
    )
    fastest = times[0] if times else 0
    tqtime = times[1] if len(times) > 1 else fastest

    if fastest < 1:
        fastest = 0

    # First/last arrival (Gap.pm line 166-173)
    arrivals = [p.get("endSS", 0) for p in active if (p.get("endSS", 0) - p.get("startSS", 0)) > 0]
    minarr = min(arrivals) if arrivals else 0
    maxarr = max(arrivals) if arrivals else 0

    # First/last departure (Gap.pm line 232-238)
    goal_departures = [p.get("startSS", 0) for p in active if p.get("startSS", 0) > 0 and p.get("goal", 0) > 0]
    firstdepart = min(goal_departures) if goal_departures else 0
    lastdepart = max(goal_departures) if goal_departures else 0

    # Min leading coefficient (Gap.pm line 199-213)
    leadingcoeff = select_coeff(formula)
    if ess > 0:
        coeffs = [p.get("coeff", 0) for p in active if (p.get("endSS", 0) - p.get("startSS", 0)) > 0 and p.get("coeff", 0) > 0]
    else:
        coeffs = [p.get("coeff", 0) for p in active if p.get("coeff", 0) > 0]
    mincoeff = min(coeffs) if coeffs else 0

    # Median distance (Gap.pm line 241-248)
    nonabs_dists = sorted([max(p.get("distance", 0), mindist) if p.get("distance", 0) > 0 else p.get("distance", 0) for p in active if p.get("result") not in ("abs", "dnf")])
    if nonabs_dists:
        mid = len(nonabs_dists) // 2
        if len(nonabs_dists) % 2 == 0 and len(nonabs_dists) > 1:
            median = (nonabs_dists[mid - 1] + nonabs_dists[mid]) / 2.0
        else:
            median = nonabs_dists[mid]
    else:
        median = 0

    # Average distance (Gap.pm line 251-257)
    active_dists = [p.get("distance", 0) for p in active if p.get("result") not in ("abs", "dnf")]
    avdist = sum(active_dists) / len(active_dists) if active_dists else 0

    # Standard deviation (Gap.pm line 132 - from SQL)
    if active_dists:
        mean_d = sum(active_dists) / len(active_dists)
        stddev = math.sqrt(sum((d - mean_d) ** 2 for d in active_dists) / len(active_dists))
    else:
        stddev = 0

    # Distance spread for difficulty (Gap.pm line 261-274)
    distspread = []
    if formula.get("diffcalc") == "lo":
        scoring_dists = [p.get("distance", 0) for p in active if p.get("result") not in ("abs", "dnf") and p.get("goal", 0) == 0]
    else:
        scoring_dists = [p.get("distance", 0) for p in active if p.get("result") not in ("abs", "dnf")]

    bucket_counts: dict[int, int] = {}
    for d in scoring_dists:
        bucket = int(d / 100)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
    for bucket_idx, count in sorted(bucket_counts.items()):
        distspread.append({"Distance": bucket_idx, "Difficulty": count})

    # Max landed-out distance (Gap.pm line 285-295)
    lo_dists = [p.get("distance", 0) + (glidebonus * p.get("stopalt", 0) if glidebonus else 0) for p in active if p.get("goal", 0) == 0]
    maxlodist = max(lo_dists) if lo_dists else mindist
    if maxlodist < mindist:
        maxlodist = mindist

    # Lookahead (Gap.pm line 297-307)
    nlo = launched - goal
    lookahead = formula.get("diffdist", 30) * 10
    if formula.get("difframp") == "flexible" and nlo > 0:
        lookahead = _round(3 * maxlodist / (100 * nlo))
        if lookahead < 30:
            lookahead = 30

    taskt = {
        "pilots": pilots_total,
        "maxdist": maxdist,
        "distance": totdist,
        "median": median,
        "avdist": avdist,
        "stddev": stddev,
        "landed": landed,
        "launched": launched,
        "launchvalid": task.get("launchvalid", 1),
        "goal": goal,
        "ess": ess,
        "fastest": fastest,
        "tqtime": tqtime,
        "firstdepart": firstdepart,
        "lastdepart": lastdepart,
        "firstarrival": minarr,
        "lastarrival": maxarr,
        "mincoeff": mincoeff,
        "distspread": distspread,
        "kmmarker": [],  # populated by caller if needed
        "stopped": task.get("stopped", 0),
        "endssdistance": task.get("endssdistance", 0),
        "lookahead": lookahead,
    }

    # Compute quality
    dv, tv, lv, sv = day_quality(taskt, formula)
    taskt["dist_validity"] = dv
    taskt["time_validity"] = tv
    taskt["launch_validity"] = lv
    taskt["stop_validity"] = sv
    taskt["quality"] = dv * tv * lv * sv

    return taskt
