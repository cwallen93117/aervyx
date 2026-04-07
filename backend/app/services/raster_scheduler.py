"""Background raster pre-generation scheduler.

Runs every 15 minutes and pre-warms the raster cache for model/variable pairs
that users have previously viewed, so subsequent visits get instant responses.

Design constraints:
- Max 50 rasters per scheduler cycle to prevent runaway fetches.
- Max 2 concurrent Herbie fetches (shared ThreadPoolExecutor from weather.py).
- Only pre-generate daytime forecast hours (no soaring at 3am).
- Model priority: HRRR -> RAP -> NAM3km -> GFS.
- Only pre-generate the "soaring essentials" variable set.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Raster version must match the value in weather.py exactly.
_RASTER_VERSION = "v8"

# How long after a model's init time before data is typically available on NOMADS.
MODEL_AVAILABILITY_DELAY: dict[str, float] = {
    "gfs": 4.0,
    "nam3km": 2.5,
    "nam": 2.0,
    "rap": 1.0,
    "hrrr": 1.0,
    "nbm": 1.5,
}

# Process models in this priority order.
MODEL_PRIORITY = ["hrrr", "rap", "nam3km", "nam", "gfs"]

# Variables to pre-generate (soaring essentials only).
PREGENERATE_VARIABLES = [
    "thermal_updraft",
    "soaring_quality",
    "boundary_layer_height",
    "cloud_cover",
    "wind_speed_10m",
]

MAX_PER_CYCLE = 50
MAX_CONCURRENT = 2
LOOP_INTERVAL_SECONDS = 15 * 60  # 15 minutes

# Shared thread pool (2 workers, same limit as weather.py's _executor).
_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)


# ---------------------------------------------------------------------------
# Solar position helper
# ---------------------------------------------------------------------------

def _is_daytime(lat: float, lon: float, utc_dt: datetime) -> bool:
    """Approximate check: is it between sunrise and sunset at this location?

    Uses the standard solar declination + hour angle formula.
    Adds a 1-hour buffer on each side (pre-sunrise thermals / post-sunset interest).
    Returns True if the UTC datetime falls within the local solar day window.
    """
    day_of_year = utc_dt.timetuple().tm_yday

    # Solar declination (degrees)
    decl_rad = math.radians(23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81))))

    # Local solar time offset from UTC (longitude / 15 degrees per hour)
    local_solar_hour = utc_dt.hour + utc_dt.minute / 60.0 + lon / 15.0

    # Hour angle (degrees) — 0 at solar noon
    hour_angle_deg = (local_solar_hour - 12.0) * 15.0
    hour_angle_rad = math.radians(hour_angle_deg)

    lat_rad = math.radians(lat)

    # cos(zenith) at this moment
    cos_zenith = (
        math.sin(lat_rad) * math.sin(decl_rad)
        + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad)
    )

    # Solar elevation angle — positive means sun is above horizon.
    # We add a 1-hour buffer equivalent (~15 degrees).
    # sin(elevation) = cos_zenith; threshold sin(-6°) ≈ -0.105 gives civil twilight.
    # Using threshold of -0.26 (≈ -15 degrees of elevation) adds ~1h buffer.
    return cos_zenith > -0.26


# ---------------------------------------------------------------------------
# Model run helpers
# ---------------------------------------------------------------------------

def _latest_available_run(model: str, now_utc: datetime, cfg: dict) -> tuple[str, str] | None:
    """Return (YYYYMMDD, HH) for the most recent run that should be available.

    Walks back through run_hours until we find one where enough time has
    elapsed for NOMADS to have the data.
    """
    delay_hours = MODEL_AVAILABILITY_DELAY.get(model, 2.0)
    run_hours = sorted(cfg["run_hours"], reverse=True)

    for day_offset in range(3):  # check today, yesterday, day before
        check_dt = now_utc - timedelta(days=day_offset)
        for rh in run_hours:
            run_dt = check_dt.replace(hour=rh, minute=0, second=0, microsecond=0)
            if run_dt > now_utc:
                continue
            elapsed_hours = (now_utc - run_dt).total_seconds() / 3600.0
            if elapsed_hours >= delay_hours:
                return run_dt.strftime("%Y%m%d"), f"{rh:02d}"

    return None


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

async def _scheduler_loop() -> None:
    """Async loop that runs every LOOP_INTERVAL_SECONDS and pre-generates rasters."""
    # Delay first run by 2 minutes to let the app finish starting up.
    await asyncio.sleep(120)

    while True:
        try:
            await _run_cycle()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("raster_scheduler: unhandled error in cycle, will retry next interval")

        await asyncio.sleep(LOOP_INTERVAL_SECONDS)


async def _run_cycle() -> None:
    """Execute one pre-generation cycle."""
    from app.routers.weather import MODEL_CONFIG, VARIABLES, _fetch_raster
    from app.services.raster_cache import get_cached_raster, store_raster
    from app.services.demand_tracker import get_active_demands

    now_utc = datetime.now(timezone.utc)
    logger.info("raster_scheduler: starting pre-generation cycle at %s", now_utc.isoformat())

    active_demands = get_active_demands(stale_days=14)
    if not active_demands:
        logger.info("raster_scheduler: no active demands, skipping cycle")
        return

    # Build a set of demanded (model, variable) pairs for quick lookup.
    demanded: set[tuple[str, str]] = {
        (d["model"], d["variable"]) for d in active_demands
    }

    # Build work queue: (model, run_date, run_hour, fxx, variable)
    work_queue: list[tuple[str, str, str, int, str]] = []

    for model in MODEL_PRIORITY:
        if model not in MODEL_CONFIG:
            continue

        cfg = MODEL_CONFIG[model]
        run_info = _latest_available_run(model, now_utc, cfg)
        if run_info is None:
            logger.debug("raster_scheduler: no available run found for %s", model)
            continue

        run_date, run_hour = run_info

        # Build the run datetime for daytime checks.
        run_dt = datetime.strptime(
            f"{run_date} {run_hour}:00", "%Y%m%d %H:%M"
        ).replace(tzinfo=timezone.utc)

        # Determine variables to pre-generate for this model.
        vars_to_generate = [
            v for v in PREGENERATE_VARIABLES
            if (model, v) in demanded
            and model not in VARIABLES.get(v, {}).get("exclude_models", [])
        ]

        if not vars_to_generate:
            continue

        # Build fxx list sorted nearest-first (small fxx = most immediately useful).
        fxx_range = range(cfg["fxx_step"], cfg["max_fxx"] + 1, cfg["fxx_step"])

        for fxx in fxx_range:
            valid_dt = run_dt + timedelta(hours=fxx)

            # Representative lat/lon for daytime check: use CONUS center (38°N, -98°W).
            if not _is_daytime(38.0, -98.0, valid_dt):
                continue

            for variable in vars_to_generate:
                cache_key = (
                    f"raster:{_RASTER_VERSION}:{model}:{run_date}:{run_hour}:{fxx}:{variable}"
                )

                # Skip if already cached.
                if get_cached_raster(cache_key) is not None:
                    continue

                work_queue.append((model, run_date, run_hour, fxx, variable))

                if len(work_queue) >= MAX_PER_CYCLE:
                    break

            if len(work_queue) >= MAX_PER_CYCLE:
                break

        if len(work_queue) >= MAX_PER_CYCLE:
            break

    if not work_queue:
        logger.info("raster_scheduler: all demanded rasters already cached")
        return

    logger.info(
        "raster_scheduler: %d rasters queued for pre-generation (max %d per cycle)",
        len(work_queue),
        MAX_PER_CYCLE,
    )

    # Process queue with max MAX_CONCURRENT concurrent fetches.
    generated = 0
    failed = 0
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    loop = asyncio.get_event_loop()

    async def _fetch_one(model: str, run_date: str, run_hour: str, fxx: int, variable: str) -> None:
        nonlocal generated, failed
        cache_key = (
            f"raster:{_RASTER_VERSION}:{model}:{run_date}:{run_hour}:{fxx}:{variable}"
        )
        async with sem:
            try:
                result = await loop.run_in_executor(
                    _executor,
                    _fetch_raster,
                    model,
                    run_date,
                    run_hour,
                    fxx,
                    variable,
                )
                store_raster(cache_key, model, run_date, run_hour, fxx, variable, result)
                logger.info(
                    "raster_scheduler: pre-generated %s %s f%03d run %s/%s",
                    model,
                    variable,
                    fxx,
                    run_date,
                    run_hour,
                )
                generated += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "raster_scheduler: failed to pre-generate %s %s f%03d run %s/%s",
                    model,
                    variable,
                    fxx,
                    run_date,
                    run_hour,
                    exc_info=True,
                )
                failed += 1

    tasks = [
        asyncio.create_task(_fetch_one(model, run_date, run_hour, fxx, variable))
        for model, run_date, run_hour, fxx, variable in work_queue
    ]

    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(
        "raster_scheduler: cycle complete — %d generated, %d failed",
        generated,
        failed,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def start_raster_scheduler() -> asyncio.Task:
    """Start the background raster pre-generation loop.

    Returns the asyncio Task so the caller can cancel it on shutdown.
    Call this from the FastAPI lifespan context (same pattern as MQTT/FAA).
    """
    task = asyncio.create_task(_scheduler_loop())
    logger.info("raster_scheduler: background task started (15-minute cycle)")
    return task
