from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import LivePosition, Pilot, User
from app.routers.tracking import admin_raw_position_history


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def test_admin_raw_position_history_includes_all_retained_app_and_mesh_rows() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin")
    pilot = Pilot(first_name="Alex", last_name="Pilot", email="alex@example.com")
    app_user = User(username="alex@example.com", full_name="Alex Pilot", role="pilot")
    session.add_all([admin, pilot, app_user])
    session.flush()
    app_user.pilot_id = pilot.id
    start = datetime(2020, 1, 1, 12, tzinfo=UTC)
    session.add_all(
        [
            LivePosition(user_id=app_user.id, lat=35.0, lon=-82.0, alt=100, timestamp=start, source="app"),
            LivePosition(pilot_id=pilot.id, lat=35.1, lon=-82.1, alt=110, timestamp=start + timedelta(seconds=10), source="mesh_relay", device_id="!abcdef01"),
            LivePosition(pilot_id=pilot.id, lat=35.2, lon=-82.2, alt=120, timestamp=start + timedelta(seconds=20), source="mqtt_gateway", device_id="!abcdef01"),
        ]
    )
    session.commit()

    first_page = admin_raw_position_history(pilot.id, limit=2, cursor=None, _=admin, session=session)

    assert [point.path for point in first_page.points] == ["MQTT gateway", "Mesh relay"]
    assert first_page.points[0].point_type == "mesh"
    assert first_page.points[1].vario_mps == 1.0
    assert first_page.next_cursor is not None

    second_page = admin_raw_position_history(pilot.id, limit=2, cursor=first_page.next_cursor, _=admin, session=session)

    assert [point.path for point in second_page.points] == ["App"]
    assert second_page.next_cursor is None
