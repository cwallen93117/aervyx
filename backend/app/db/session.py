from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine_kwargs = {
    "future": True,
    "connect_args": connect_args,
}

# QNAP/Postgres can briefly restart during recovery. Pre-ping and recycle stale
# pooled connections so login and API requests recover instead of hanging on a
# dead socket.
if not settings.database_url.startswith("sqlite"):
    engine_kwargs.update(
        {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_use_lifo": True,
            "pool_size": 10,
            "max_overflow": 20,
            "pool_timeout": 30,
        }
    )

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
