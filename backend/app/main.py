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


