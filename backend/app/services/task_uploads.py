from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Event, IGCUpload, ScoreResult, Task, TaskScoringInput, TrackPoint
from app.services.audit import log_action
from app.services.igc import ParsedIGC, parse_igc
from app.services.logbook import sync_task_upload_to_logbook
from app.services.scoring import rescore_task
from app.services.tracking import _publish


@dataclass
class StoredUpload:
    upload: IGCUpload
    created: bool


def normalized_upload_source(value: str | None) -> str:
    normalized = str(value or "manual").strip().lower()
    if normalized == "auto":
        return "bulk"
    return normalized or "manual"


def manual_filename_with_suffix(session: Session, task_id: int, pilot_id: int, filename: str) -> str:
    existing = {
        str(name)
        for name in session.scalars(
            select(IGCUpload.filename).where(
                IGCUpload.task_id == task_id,
                IGCUpload.pilot_id == pilot_id,
            )
        ).all()
    }
    if filename not in existing:
        return filename
    path = Path(filename)
    base = path.stem
    suffix = path.suffix or ""
    match = re.match(r"^(.*?)(\d+)$", base)
    if match:
        root = match.group(1)
        counter = int(match.group(2))
    else:
        root = base
        counter = 1
    while True:
        counter += 1
        candidate = f"{root}{counter}{suffix}"
        if candidate not in existing:
            return candidate


def is_late_start_upload(session: Session, task: Task, upload: IGCUpload) -> bool:
    """Return True if the upload's first fix is after the task's start_close_time."""
    if not task.start_close_time:
        return False
    first_fix_time = session.scalar(
        select(func.min(TrackPoint.recorded_at)).where(TrackPoint.upload_id == upload.id)
    )
    if first_fix_time is None:
        return False
    try:
        parts = task.start_close_time.split(":")
        close_time = dt_time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    except (ValueError, IndexError):
        return False
    event = session.get(Event, task.event_id)
    try:
        tz = ZoneInfo(event.timezone if event else "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_fix = first_fix_time.astimezone(tz).time()
    return local_fix > close_time


def select_upload_for_scoring(
    session: Session,
    task: Task,
    pilot_id: int,
    upload: IGCUpload,
    updated_by_user_id: int,
) -> bool:
    existing_input = session.scalar(
        select(TaskScoringInput).where(
            TaskScoringInput.task_id == task.id,
            TaskScoringInput.pilot_id == pilot_id,
        )
    )
    if existing_input is None:
        session.add(TaskScoringInput(
            task_id=task.id,
            pilot_id=pilot_id,
            selected_upload_id=upload.id,
            updated_by_user_id=updated_by_user_id,
        ))
        session.flush()
        return True

    changed = existing_input.selected_upload_id != upload.id or existing_input.status_override is not None
    if changed:
        existing_input.selected_upload_id = upload.id
        existing_input.status_override = None
        existing_input.updated_by_user_id = updated_by_user_id
        session.flush()
    return changed


def auto_select_and_rescore(
    session: Session,
    task: Task,
    pilot_id: int,
    upload: IGCUpload,
    uploaded_by_user_id: int,
) -> None:
    """If the task has been scored, auto-select the newest upload and rescore.

    Late-start uploads are not auto-selected; they remain available in the
    scoring dropdown while the existing selection stays in place.
    """
    if is_late_start_upload(session, task, upload):
        return

    has_scored = (
        session.scalar(
            select(func.count()).select_from(ScoreResult).where(ScoreResult.task_id == task.id)
        )
        or 0
    ) > 0

    existing_input = session.scalar(
        select(TaskScoringInput).where(
            TaskScoringInput.task_id == task.id,
            TaskScoringInput.pilot_id == pilot_id,
        )
    )
    if existing_input is None and not has_scored:
        return

    changed = select_upload_for_scoring(session, task, pilot_id, upload, uploaded_by_user_id)
    if changed and has_scored:
        rescore_task(session, task.id)
        log_action(
            session,
            actor_user_id=uploaded_by_user_id,
            action="task.auto_rescore",
            entity_type="task",
            entity_id=str(task.id),
            details={"pilot_id": pilot_id, "upload_id": upload.id, "trigger": "new_upload"},
        )


async def store_task_upload(
    session: Session,
    task: Task,
    *,
    filename: str,
    content: bytes,
    pilot_id: int,
    uploaded_by_user_id: int,
    upload_source: str = "manual",
    auto_select_and_rescore_enabled: bool = True,
    parsed: ParsedIGC | None = None,
) -> StoredUpload:
    sha256 = hashlib.sha256(content).hexdigest()
    parsed = parsed or parse_igc(content)

    existing = session.scalar(
        select(IGCUpload).where(
            IGCUpload.task_id == task.id,
            IGCUpload.pilot_id == pilot_id,
            IGCUpload.sha256 == sha256,
        )
    )
    if existing is not None:
        metadata = dict(existing.metadata_json or {})
        metadata.update(parsed.metadata)
        parsed.metadata.clear()
        parsed.metadata.update(metadata)
        sync_task_upload_to_logbook(session, upload=existing, parsed=parsed)
        if auto_select_and_rescore_enabled:
            auto_select_and_rescore(session, task, pilot_id, existing, uploaded_by_user_id)
        return StoredUpload(upload=existing, created=False)

    safe_filename = filename or "track.igc"
    normalized_source = normalized_upload_source(upload_source)
    if normalized_source == "manual":
        safe_filename = manual_filename_with_suffix(session, task.id, pilot_id, safe_filename)
    parsed.metadata["upload_source"] = normalized_source
    settings = get_settings()
    upload_dir = Path(settings.upload_root) / "igc" / sha256
    await asyncio.to_thread(upload_dir.mkdir, parents=True, exist_ok=True)
    stored_path = upload_dir / safe_filename
    if not await asyncio.to_thread(stored_path.exists):
        await asyncio.to_thread(stored_path.write_bytes, content)
    upload = IGCUpload(
        event_id=task.event_id,
        task_id=task.id,
        pilot_id=pilot_id,
        uploaded_by_user_id=uploaded_by_user_id,
        filename=safe_filename,
        sha256=sha256,
        stored_path=str(stored_path),
        metadata_json=parsed.metadata,
    )
    session.add(upload)
    session.flush()
    for sequence, fix in enumerate(parsed.fixes, start=1):
        session.add(
            TrackPoint(
                upload_id=upload.id,
                sequence=sequence,
                recorded_at=fix.recorded_at,
                latitude=fix.latitude,
                longitude=fix.longitude,
                pressure_altitude_m=fix.pressure_altitude_m,
                gps_altitude_m=fix.gps_altitude_m,
            )
        )
    log_action(
        session,
        actor_user_id=uploaded_by_user_id,
        action="igc.upload",
        entity_type="igc_upload",
        entity_id=str(upload.id),
        details={
            "task_id": task.id,
            "pilot_id": pilot_id,
            "sha256": sha256,
            "fix_count": parsed.metadata.get("fix_count"),
            "upload_source": normalized_source,
        },
    )
    sync_task_upload_to_logbook(session, upload=upload, parsed=parsed)
    _publish(task.id, {
        "event": "igc_available",
        "task_id": task.id,
        "pilot_id": pilot_id,
        "upload_id": upload.id,
    })
    if auto_select_and_rescore_enabled:
        auto_select_and_rescore(session, task, pilot_id, upload, uploaded_by_user_id)
    return StoredUpload(upload=upload, created=True)
