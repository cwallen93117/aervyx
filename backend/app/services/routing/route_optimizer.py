"""TSP solver with time windows for driver pilot pickup routing.

Uses a greedy nearest-neighbor heuristic with 2-opt local improvement.
Designed for small N (<=10 pilots per driver) where this is near-optimal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.services.routing.valhalla_client import MatrixEntry

_logger = logging.getLogger(__name__)

# Assumed time to complete a pickup (load gear, etc.)
PICKUP_DURATION_SECONDS = 300  # 5 minutes

# Maximum extra wait beyond ready_at before fairness penalty kicks in
MAX_EXTRA_WAIT_SECONDS = 900  # 15 minutes

# Weight for waiting time in the greedy score (lower = prefer short drives over short waits)
WAIT_WEIGHT = 0.5


@dataclass
class PickupTarget:
    pilot_id: int
    pilot_name: str
    landing_id: int
    lat: float
    lon: float
    ready_at: datetime
    landed_at: datetime
    status: str


@dataclass
class OptimizedStop:
    target: PickupTarget
    eta: datetime
    wait_seconds: float  # time driver waits for pilot to be ready
    travel_seconds: float  # driving time to this stop
    distance_km: float  # driving distance to this stop


def optimize_route(
    targets: list[PickupTarget],
    matrix: list[list[MatrixEntry]],
    now: datetime,
) -> list[OptimizedStop]:
    """Compute optimal pickup order.

    matrix[0] is driver position to all targets.
    matrix[i+1] is target[i] to all targets.

    Matrix shape: (1 + len(targets)) sources x len(targets) targets.
    """
    if not targets:
        return []

    n = len(targets)
    if n == 1:
        t = targets[0]
        entry = matrix[0][0]
        arrival = now + timedelta(seconds=entry.time)
        wait = max(0, (t.ready_at - arrival).total_seconds())
        return [
            OptimizedStop(
                target=t,
                eta=max(arrival, t.ready_at),
                wait_seconds=wait,
                travel_seconds=entry.time,
                distance_km=entry.distance,
            )
        ]

    # Greedy construction
    order = _greedy_construction(targets, matrix, now)

    # 2-opt local improvement
    order = _two_opt_improve(order, targets, matrix, now)

    # Build final schedule
    return _build_schedule(order, targets, matrix, now)


def _greedy_construction(
    targets: list[PickupTarget],
    matrix: list[list[MatrixEntry]],
    now: datetime,
) -> list[int]:
    """Greedy nearest-neighbor with time-window awareness."""
    n = len(targets)
    remaining = set(range(n))
    order: list[int] = []
    current_matrix_idx = 0  # Start from driver position (row 0)
    current_time = now

    while remaining:
        best_idx = -1
        best_score = float("inf")

        for idx in remaining:
            entry = matrix[current_matrix_idx][idx]
            travel_time = entry.time
            arrival = current_time + timedelta(seconds=travel_time)
            wait = max(0, (targets[idx].ready_at - arrival).total_seconds())
            score = travel_time + WAIT_WEIGHT * wait

            # Heavy penalty if pilot would wait too long past ready_at
            pilot_wait = max(0, (arrival - targets[idx].ready_at).total_seconds())
            if pilot_wait > MAX_EXTRA_WAIT_SECONDS:
                score += (pilot_wait - MAX_EXTRA_WAIT_SECONDS) * 2.0

            if score < best_score:
                best_score = score
                best_idx = idx

        order.append(best_idx)
        remaining.remove(best_idx)

        # Update time: travel + wait + pickup
        entry = matrix[current_matrix_idx][best_idx]
        arrival = current_time + timedelta(seconds=entry.time)
        departure = max(arrival, targets[best_idx].ready_at) + timedelta(
            seconds=PICKUP_DURATION_SECONDS
        )
        current_time = departure
        current_matrix_idx = best_idx + 1  # +1 because row 0 is driver

    return order


def _two_opt_improve(
    order: list[int],
    targets: list[PickupTarget],
    matrix: list[list[MatrixEntry]],
    now: datetime,
) -> list[int]:
    """Try swapping adjacent pairs to reduce total time."""
    if len(order) <= 2:
        return order

    best_order = order[:]
    best_cost = _total_cost(best_order, targets, matrix, now)

    improved = True
    max_iterations = 50  # Safety bound
    iteration = 0

    while improved and iteration < max_iterations:
        improved = False
        iteration += 1
        for i in range(len(best_order) - 1):
            candidate = best_order[:]
            candidate[i], candidate[i + 1] = candidate[i + 1], candidate[i]
            cost = _total_cost(candidate, targets, matrix, now)
            if cost < best_cost:
                # Verify fairness constraint
                schedule = _build_schedule(candidate, targets, matrix, now)
                if _passes_fairness(schedule):
                    best_order = candidate
                    best_cost = cost
                    improved = True

    return best_order


def _total_cost(
    order: list[int],
    targets: list[PickupTarget],
    matrix: list[list[MatrixEntry]],
    now: datetime,
) -> float:
    """Total time cost for a given order (drive + wait)."""
    current_time = now
    current_row = 0
    total = 0.0

    for idx in order:
        entry = matrix[current_row][idx]
        arrival = current_time + timedelta(seconds=entry.time)
        wait = max(0, (targets[idx].ready_at - arrival).total_seconds())
        total += entry.time + WAIT_WEIGHT * wait

        departure = max(arrival, targets[idx].ready_at) + timedelta(
            seconds=PICKUP_DURATION_SECONDS
        )
        current_time = departure
        current_row = idx + 1

    return total


def _passes_fairness(schedule: list[OptimizedStop]) -> bool:
    """Ensure no pilot waits too long past their ready_at."""
    for stop in schedule:
        pilot_wait = (stop.eta - stop.target.ready_at).total_seconds()
        if pilot_wait > MAX_EXTRA_WAIT_SECONDS:
            return False
    return True


def _build_schedule(
    order: list[int],
    targets: list[PickupTarget],
    matrix: list[list[MatrixEntry]],
    now: datetime,
) -> list[OptimizedStop]:
    """Build the final schedule from an ordered index list."""
    schedule: list[OptimizedStop] = []
    current_time = now
    current_row = 0

    for idx in order:
        entry = matrix[current_row][idx]
        arrival = current_time + timedelta(seconds=entry.time)
        wait = max(0, (targets[idx].ready_at - arrival).total_seconds())
        eta = max(arrival, targets[idx].ready_at)

        schedule.append(
            OptimizedStop(
                target=targets[idx],
                eta=eta,
                wait_seconds=wait,
                travel_seconds=entry.time,
                distance_km=entry.distance,
            )
        )

        departure = eta + timedelta(seconds=PICKUP_DURATION_SECONDS)
        current_time = departure
        current_row = idx + 1

    return schedule
