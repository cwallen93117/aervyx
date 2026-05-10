from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Event, Pilot, ScoreResult, Task, User
from app.routers.results import task_result_summary


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


def _score(task: Task, pilot: Pilot, quality: float | None, state: str = "official") -> ScoreResult:
    details_json = {}
    if quality is not None:
        details_json = {"gap": {"validity": {"overall": quality}}}
    return ScoreResult(
        task_id=task.id,
        pilot_id=pilot.id,
        status="goal",
        rank=1,
        distance_flown_km=40,
        raw_score_points=900,
        score_points=900,
        details_json=details_json,
        result_state=state,
    )


def test_task_result_summary_returns_day_quality_for_each_scored_task() -> None:
    session = _session()
    admin = User(username="admin@example.com", full_name="Admin", role="admin", password_hash="hash")
    event = Event(
        name="Spring Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([admin, event, pilot])
    session.flush()
    tasks = [Task(event_id=event.id, name=f"Task {index}") for index in range(1, 4)]
    session.add_all(tasks)
    session.flush()
    session.add_all([
        _score(tasks[0], pilot, 1.0),
        _score(tasks[1], pilot, 0.5805),
        _score(tasks[2], pilot, None),
    ])
    session.flush()

    summaries = task_result_summary(event.id, user=admin, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in summaries] == [
        (tasks[0].id, 1.0),
        (tasks[1].id, 0.5805),
        (tasks[2].id, None),
    ]


def test_task_result_summary_hides_provisional_scores_from_pilots() -> None:
    session = _session()
    viewer = User(username="viewer@example.com", full_name="Viewer", role="pilot", password_hash="hash")
    event = Event(
        name="Public Race",
        location="Ridgeline",
        starts_on=date(2026, 4, 18),
        ends_on=date(2026, 4, 24),
        timezone="America/New_York",
    )
    pilot = Pilot(first_name="Ada", last_name="Wing")
    session.add_all([viewer, event, pilot])
    session.flush()
    official_task = Task(event_id=event.id, name="Official Task")
    provisional_task = Task(event_id=event.id, name="Provisional Task")
    session.add_all([official_task, provisional_task])
    session.flush()
    session.add_all([
        _score(official_task, pilot, 0.5536, state="official"),
        _score(provisional_task, pilot, 0.75, state="provisional"),
    ])
    session.flush()

    summaries = task_result_summary(event.id, user=viewer, session=session)

    assert [(summary.task_id, summary.day_quality) for summary in summaries] == [
        (official_task.id, 0.5536),
    ]
