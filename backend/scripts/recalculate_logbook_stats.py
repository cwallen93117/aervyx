import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine
from app.models import PilotFlight
from app.services.logbook import recompute_track_backed_flight_stats


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    updated_count = 0
    skipped_count = 0
    try:
        flights = session.query(PilotFlight).filter(PilotFlight.source_kind.in_(("app_upload", "task_upload"))).order_by(PilotFlight.id.asc()).all()
        for flight in flights:
            if recompute_track_backed_flight_stats(session, flight):
                updated_count += 1
            else:
                skipped_count += 1
        session.commit()
        print(f"Recalculated logbook stats for {updated_count} track-backed flights; skipped {skipped_count} flights with no track points.")
    finally:
        session.close()
