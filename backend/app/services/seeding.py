from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Event, EventPilot, Pilot, Task, TaskPoint, Turnpoint, User

DEFAULT_ADMIN_PASSWORD = "admin1234"
DEFAULT_PILOT_PASSWORD = "pilot1234"


def bootstrap_demo_data(session: Session) -> None:
    admin = session.scalar(select(User).where(User.username == "admin"))
    if admin is None:
        session.add(User(username="admin", full_name="Flight Director", role="admin", password_hash=hash_password(DEFAULT_ADMIN_PASSWORD)))

    demo_pilot = session.scalar(select(User).where(User.username == "pilot-demo"))
    if demo_pilot is None:
        pilot = Pilot(first_name="Demo", last_name="Pilot", email="pilot@example.com", nation="USA", competition_number="101", civl_id="DEMO101")
        session.add(pilot)
        session.flush()
        session.add(User(username="pilot-demo", full_name="Demo Pilot", role="pilot", pilot_id=pilot.id, password_hash=hash_password(DEFAULT_PILOT_PASSWORD)))

    event = session.scalar(select(Event).where(Event.name == "Spring Ridge Open"))
    if event is None:
        event = Event(
            name="Spring Ridge Open",
            location="Owens Valley, CA",
            starts_on=date(2026, 4, 18),
            ends_on=date(2026, 4, 24),
            timezone="America/Los_Angeles",
            scoring_formula="GAP2021",
            nominal_distance_km=72,
            nominal_time_hours=1.8,
            nominal_launch=0.95,
            minimum_distance_km=5,
            nominal_goal_percent=0.3,
            score_back_time_minutes=15,
            goal_ss_penalty=0,
            jump_the_gun_factor=0,
            jump_the_gun_max_seconds=0,
            stopped_glide_bonus=0,
            use_distance_points=True,
            use_time_points=True,
            use_leading_points=True,
            use_arrival_position_points=False,
            use_arrival_time_points=False,
            use_departure_points=False,
            penalties_json={"jump_the_gun": 0, "airspace": 0},
        )
        session.add(event)
        session.flush()
        pilot = session.scalar(select(Pilot).where(Pilot.competition_number == "101"))
        if pilot is not None:
            session.add(EventPilot(event_id=event.id, pilot_id=pilot.id))
        launch = Turnpoint(event_id=event.id, name="Launch Ridge", code="LCH", latitude=36.606, longitude=-118.062, elevation_m=1900)
        start = Turnpoint(event_id=event.id, name="Start Cylinder", code="ST1", latitude=36.650, longitude=-118.095, elevation_m=1700)
        turn = Turnpoint(event_id=event.id, name="Tableland", code="TP1", latitude=36.725, longitude=-118.210, elevation_m=1650)
        ess = Turnpoint(event_id=event.id, name="ESS Valley", code="ESS", latitude=36.788, longitude=-118.280, elevation_m=1600)
        goal = Turnpoint(event_id=event.id, name="Goal Field", code="GL1", latitude=36.810, longitude=-118.320, elevation_m=1500)
        session.add_all([launch, start, turn, ess, goal])
        session.flush()
        task = Task(
            event_id=event.id,
            name="Task 1",
            status="published",
            task_type="race_to_goal",
            task_start_time="13:30:00",
            task_finish_time="17:45:00",
            start_open_time="14:00:00",
            start_close_time="16:00:00",
            start_gate_count=1,
            start_gate_interval_seconds=None,
            nominal_distance_km=event.nominal_distance_km or 72,
            nominal_time_hours=event.nominal_time_hours or 1.8,
            nominal_launch=event.nominal_launch or 0.95,
            minimum_distance_km=event.minimum_distance_km or 5,
            penalties_json=event.penalties_json or {},
        )
        session.add(task)
        session.flush()
        session.add_all([
            TaskPoint(task_id=task.id, position=1, point_type="launch", radius_m=300, turnpoint_id=launch.id, name=launch.name, latitude=launch.latitude, longitude=launch.longitude),
            TaskPoint(task_id=task.id, position=2, point_type="start", radius_m=1000, turnpoint_id=start.id, name=start.name, latitude=start.latitude, longitude=start.longitude),
            TaskPoint(task_id=task.id, position=3, point_type="turnpoint", radius_m=400, turnpoint_id=turn.id, name=turn.name, latitude=turn.latitude, longitude=turn.longitude),
            TaskPoint(task_id=task.id, position=4, point_type="ESS", radius_m=1000, turnpoint_id=ess.id, name=ess.name, latitude=ess.latitude, longitude=ess.longitude),
            TaskPoint(task_id=task.id, position=5, point_type="goal", radius_m=200, turnpoint_id=goal.id, name=goal.name, latitude=goal.latitude, longitude=goal.longitude),
        ])
