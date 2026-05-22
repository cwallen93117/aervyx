from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.routers import admin_db, admin_integrations, airspace, app_release, auth, events, logbook, map_overlay_config, pilots, public, results, site_settings, sites, tasks, turnpoints, uploads
from app.services.pilot_identity import repair_pilot_email_identities
from app.services.seeding import bootstrap_demo_data

try:
    from app.routers import tracking
except ImportError:
    tracking = None

try:
    from app.routers import buddies
except ImportError:
    buddies = None

try:
    from app.routers import admin_debug
except ImportError:
    admin_debug = None

try:
    from app.routers import admin_sos
except ImportError:
    admin_sos = None

try:
    from app.routers import driver_routing
except ImportError:
    driver_routing = None

try:
    from app.routers import weather
except ImportError:
    weather = None

try:
    from app.services.raster_cache import prune_old_rasters
except ImportError:
    prune_old_rasters = None

try:
    from app.routers import faa_airspace as faa_airspace_router
except ImportError:
    faa_airspace_router = None

try:
    from app.services.mqtt_subscriber import start_mqtt_subscriber
except ImportError:
    start_mqtt_subscriber = None

try:
    from app.services.tracking import prune_old_live_positions, start_live_position_pruner
except ImportError:
    prune_old_live_positions = None
    start_live_position_pruner = None

try:
    from app.services.faa_airspace import start_faa_airspace_refresh
except ImportError:
    start_faa_airspace_refresh = None

try:
    from app.services.raster_scheduler import start_raster_scheduler
except ImportError:
    start_raster_scheduler = None

try:
    from app.services.cloudflare_ddns import start_cloudflare_ddns_sync
except ImportError:
    start_cloudflare_ddns_sync = None

try:
    from app.services.demand_tracker import prune_stale_demands
except ImportError:
    prune_stale_demands = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    import logging as _logging
    _log = _logging.getLogger(__name__)

    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    session = SessionLocal()
    try:
        bootstrap_demo_data(session)
        repaired_identities = repair_pilot_email_identities(session)
        if repaired_identities:
            _log.info("Repaired %d pilot email identities on startup", repaired_identities)
        session.commit()
    finally:
        session.close()

    # Prune old raster cache entries on startup
    if prune_old_rasters is not None:
        try:
            pruned = prune_old_rasters(keep_days=2)
            if pruned:
                _log.info("Pruned %d old raster cache entries on startup", pruned)
        except Exception:
            _log.warning("Raster cache prune failed on startup", exc_info=True)

    # Prune stale demand tracking rows on startup
    if prune_stale_demands is not None:
        try:
            pruned_d = prune_stale_demands(stale_days=30)
            if pruned_d:
                _log.info("Pruned %d stale demand tracker entries on startup", pruned_d)
        except Exception:
            _log.warning("Demand tracker prune failed on startup", exc_info=True)

    # Prune old live tracking rows on startup; IGC/TrackPoint data is permanent.
    if prune_old_live_positions is not None:
        try:
            pruned_live = prune_old_live_positions()
            if pruned_live:
                _log.info("Pruned %d old live position rows on startup", pruned_live)
        except Exception:
            _log.warning("Live position prune failed on startup", exc_info=True)

    mqtt_task = await start_mqtt_subscriber() if start_mqtt_subscriber is not None else None
    live_position_prune_task = await start_live_position_pruner() if start_live_position_pruner is not None else None
    faa_task = await start_faa_airspace_refresh() if start_faa_airspace_refresh is not None else None
    raster_task = await start_raster_scheduler() if start_raster_scheduler is not None else None
    cloudflare_ddns_task = await start_cloudflare_ddns_sync() if start_cloudflare_ddns_sync is not None else None
    yield
    if mqtt_task is not None:
        mqtt_task.cancel()
    if live_position_prune_task is not None:
        live_position_prune_task.cancel()
    if faa_task is not None:
        faa_task.cancel()
    if raster_task is not None:
        raster_task.cancel()
    if cloudflare_ddns_task is not None:
        cloudflare_ddns_task.cancel()


settings = get_settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[])
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests. Please wait before trying again."},
    )


if settings.app_env.lower() == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=(
        None
        if settings.app_env.lower() == "production"
        else r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+)(:\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(admin_db.router)
app.include_router(admin_integrations.router)
app.include_router(auth.router)
app.include_router(site_settings.router)
app.include_router(map_overlay_config.router)
app.include_router(sites.router)
app.include_router(public.router)
app.include_router(events.router)
app.include_router(pilots.router)
app.include_router(turnpoints.router)
app.include_router(airspace.router)
app.include_router(tasks.router)
app.include_router(uploads.router)
app.include_router(results.router)
app.include_router(logbook.router)
app.include_router(app_release.router)
if tracking is not None:
    app.include_router(tracking.router)
if buddies is not None:
    app.include_router(buddies.router)
if admin_debug is not None:
    app.include_router(admin_debug.router)
if admin_sos is not None:
    app.include_router(admin_sos.router)
if driver_routing is not None:
    app.include_router(driver_routing.router)
if weather is not None:
    app.include_router(weather.router)
if faa_airspace_router is not None:
    app.include_router(faa_airspace_router.router)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


