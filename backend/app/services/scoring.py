from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import IGCUpload, Pilot, ScoreResult, TaskPoint, TrackPoint


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return 2 * radius_km * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _to_xy_km(latitude: float, longitude: float, reference_latitude: float, reference_longitude: float) -> tuple[float, float]:
    x = (longitude - reference_longitude) * 111.32 * math.cos(math.radians(reference_latitude))
    y = (latitude - reference_latitude) * 110.57
    return x, y


def _project_progress(prev_point: TaskPoint, next_point: TaskPoint, trackpoints: list[TrackPoint]) -> float:
    leg_distance = haversine_km(prev_point.latitude, prev_point.longitude, next_point.latitude, next_point.longitude)
    if leg_distance <= 0:
        return 0.0
    bx, by = _to_xy_km(next_point.latitude, next_point.longitude, prev_point.latitude, prev_point.longitude)
    length_sq = bx * bx + by * by
    if length_sq <= 0:
        return 0.0
    best = 0.0
    for trackpoint in trackpoints:
        px, py = _to_xy_km(trackpoint.latitude, trackpoint.longitude, prev_point.latitude, prev_point.longitude)
        projection = (px * bx + py * by) / length_sq
        best = max(best, min(max(projection, 0.0), 1.0))
    return best * leg_distance


def evaluate_task(task_points: list[TaskPoint], trackpoints: list[TrackPoint]) -> dict:
    ordered_points = sorted(task_points, key=lambda point: point.position)
    if len(ordered_points) < 2:
        return {"status": "uploaded", "distance_flown_km": 0.0, "details": {"hits": []}}

    hit_indices: dict[int, int] = {}
    hit_times: dict[int, datetime] = {}
    cursor = 0
    for point in ordered_points:
        radius_km = point.radius_m / 1000.0
        for idx in range(cursor, len(trackpoints)):
            trackpoint = trackpoints[idx]
            distance = haversine_km(trackpoint.latitude, trackpoint.longitude, point.latitude, point.longitude)
            if distance <= radius_km:
                hit_indices[point.id] = idx
                hit_times[point.id] = trackpoint.recorded_at
                cursor = idx
                break

    total_distance = 0.0
    progress_distance = 0.0
    for index in range(1, len(ordered_points)):
        previous_point = ordered_points[index - 1]
        current_point = ordered_points[index]
        leg_distance = haversine_km(previous_point.latitude, previous_point.longitude, current_point.latitude, current_point.longitude)
        total_distance += leg_distance
        if current_point.id in hit_indices:
            progress_distance += leg_distance
            continue
        if previous_point.id in hit_indices:
            progress_distance += _project_progress(previous_point, current_point, trackpoints[hit_indices[previous_point.id]:])
        break

    start_point = next((point for point in ordered_points if point.point_type == "start"), None)
    ess_point = next((point for point in ordered_points if point.point_type == "ESS"), None)
    goal_point = next((point for point in ordered_points if point.point_type == "goal"), None)
    started_at = hit_times.get(start_point.id) if start_point else None
    ess_at = hit_times.get(ess_point.id) if ess_point else None
    goal_at = hit_times.get(goal_point.id) if goal_point else None

    if goal_at is not None:
        status = "goal"
    elif ess_at is not None:
        status = "ess"
    elif progress_distance > 0:
        status = "partial"
    else:
        status = "uploaded"

    elapsed_seconds = int(((goal_at or ess_at) - started_at).total_seconds()) if started_at and (goal_at or ess_at) else None
    completion_ratio = progress_distance / total_distance if total_distance else 0.0
    score_points = round(completion_ratio * 1000, 2)
    if status == "goal" and elapsed_seconds is not None:
        score_points += max(0, 300 - (elapsed_seconds / 60.0))

    return {
        "status": status,
        "distance_flown_km": round(progress_distance, 3),
        "started_at": started_at,
        "ess_at": ess_at,
        "goal_at": goal_at,
        "elapsed_seconds": elapsed_seconds,
        "score_points": round(score_points, 2),
        "details": {
            "hits": [
                {
                    "task_point_id": point.id,
                    "name": point.name,
                    "point_type": point.point_type,
                    "hit": point.id in hit_indices,
                    "hit_at": hit_times.get(point.id).isoformat() if point.id in hit_times else None,
                }
                for point in ordered_points
            ],
            "total_distance_km": round(total_distance, 3),
        },
    }


def score_upload(session: Session, upload: IGCUpload) -> ScoreResult:
    task_points = session.scalars(select(TaskPoint).where(TaskPoint.task_id == upload.task_id).order_by(TaskPoint.position)).all()
    trackpoints = session.scalars(select(TrackPoint).where(TrackPoint.upload_id == upload.id).order_by(TrackPoint.sequence)).all()
    evaluation = evaluate_task(task_points, trackpoints)
    result = session.scalar(select(ScoreResult).where(ScoreResult.task_id == upload.task_id, ScoreResult.pilot_id == upload.pilot_id))
    if result is None:
        result = ScoreResult(task_id=upload.task_id, pilot_id=upload.pilot_id, upload_id=upload.id)
        session.add(result)
    result.upload_id = upload.id
    result.status = evaluation["status"]
    result.distance_flown_km = evaluation["distance_flown_km"]
    result.started_at = evaluation.get("started_at")
    result.ess_at = evaluation.get("ess_at")
    result.goal_at = evaluation.get("goal_at")
    result.elapsed_seconds = evaluation.get("elapsed_seconds")
    result.score_points = evaluation["score_points"]
    result.details_json = evaluation["details"]
    session.flush()
    return result


def rescore_task(session: Session, task_id: int) -> list[ScoreResult]:
    uploads = session.scalars(select(IGCUpload).where(IGCUpload.task_id == task_id).order_by(IGCUpload.uploaded_at)).all()
    latest_by_pilot: dict[int, IGCUpload] = {}
    for upload in uploads:
        latest_by_pilot[upload.pilot_id] = upload
    session.execute(delete(ScoreResult).where(ScoreResult.task_id == task_id))
    session.flush()
    results = [score_upload(session, upload) for upload in latest_by_pilot.values()]
    results.sort(
        key=lambda result: (
            {"goal": 0, "ess": 1, "partial": 2, "uploaded": 3}.get(result.status, 4),
            -(result.distance_flown_km or 0),
            result.elapsed_seconds or 10**9,
            -(result.score_points or 0),
        )
    )
    for rank, result in enumerate(results, start=1):
        result.rank = rank
    session.flush()
    return results


def build_result_payload(session: Session, result: ScoreResult) -> dict:
    pilot = session.get(Pilot, result.pilot_id)
    pilot_name = f"{pilot.first_name} {pilot.last_name}" if pilot else "Unknown"
    return {
        "id": result.id,
        "task_id": result.task_id,
        "pilot_id": result.pilot_id,
        "upload_id": result.upload_id,
        "pilot_name": pilot_name,
        "competition_number": pilot.competition_number if pilot else None,
        "status": result.status,
        "rank": result.rank,
        "distance_flown_km": result.distance_flown_km,
        "started_at": result.started_at,
        "ess_at": result.ess_at,
        "goal_at": result.goal_at,
        "elapsed_seconds": result.elapsed_seconds,
        "score_points": result.score_points,
        "details_json": result.details_json,
    }