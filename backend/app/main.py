from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db import Base, SessionLocal, engine, ensure_runtime_schema
from app.routers import auth, events, pilots, results, tasks, turnpoints, uploads
from app.services.seeding import bootstrap_demo_data


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
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(events.router)
app.include_router(pilots.router)
app.include_router(turnpoints.router)
app.include_router(tasks.router)
app.include_router(uploads.router)
app.include_router(results.router)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}
