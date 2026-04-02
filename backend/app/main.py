from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import get_settings
from app.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.routers import admin_db, airspace, app_release, auth, events, logbook, pilots, public, results, site_settings, sites, tasks, turnpoints, uploads
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
    from app.services.mqtt_subscriber import start_mqtt_subscriber
except ImportError:
    start_mqtt_subscriber = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_runtime_schema(engine)
    session = SessionLocal()
    try:
        bootstrap_demo_data(session)
        session.commit()
    finally:
        session.close()
    mqtt_task = await start_mqtt_subscriber() if start_mqtt_subscriber is not None else None
    yield
    if mqtt_task is not None:
        mqtt_task.cancel()


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(admin_db.router)
app.include_router(auth.router)
app.include_router(site_settings.router)
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


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/debug/route-test')
def debug_route_test():
    """Temporary diagnostic endpoint to verify AirScore route optimizer."""
    from app.services.airscore.track_lib import to_rad_dict, distance as vincenty_distance
    from app.services.airscore.route import find_shortest_route, task_distance

    # HC 2025 Task 4 turnpoints
    waypoints = [
        to_rad_dict(39.17217, -75.96996, radius=3000.0, type='start', how='exit', shape='circle'),
        to_rad_dict(39.30175, -75.79859, radius=2000.0, type='turnpoint', how='entry', shape='circle'),
        to_rad_dict(39.44303, -75.73191, radius=400.0, type='goal', how='entry', shape='circle'),
    ]

    shortest = find_shortest_route(waypoints)
    for i, wpt in enumerate(waypoints):
        if i < len(shortest):
            wpt['short_lat'] = shortest[i]['lat']
            wpt['short_long'] = shortest[i]['long']
        else:
            wpt['short_lat'] = wpt['lat']
            wpt['short_long'] = wpt['long']

    spt, ept, gpt, ssdist, startssdist, endssdist, totdist = task_distance(waypoints)

    # Center-to-center for comparison
    cc_dist = vincenty_distance(waypoints[0], waypoints[1]) + vincenty_distance(waypoints[1], waypoints[2])

    return {
        'optimized_distance_km': round(totdist / 1000.0, 3),
        'center_to_center_km': round(cc_dist / 1000.0, 3),
        'spt': spt, 'ept': ept, 'gpt': gpt,
        'shortest_count': len(shortest),
        'short_positions': [
            {'lat': s.get('lat', 0), 'long': s.get('long', 0), 'dlat': s.get('dlat', 0), 'dlong': s.get('dlong', 0)}
            for s in shortest
        ],
        'original_positions': [
            {'lat': w['lat'], 'long': w['long']}
            for w in waypoints
        ],
    }
