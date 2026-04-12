"""Admin SOS alert management endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.deps import require_admin
from app.models import Pilot, SosAlert, User

router = APIRouter(tags=["admin-sos"])

_VALID_STATUSES = {"active", "acknowledged", "resolved"}


# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------

class SosAlertDetail(BaseModel):
    id: str
    pilot_id: int | None
    pilot_name: str | None
    lat: float
    lon: float
    alt: float | None
    message: str | None
    timestamp: str
    created_at: str
    status: str
    acknowledged_at: str | None
    resolved_at: str | None
    resolved_by: str | None
    notes: str | None


class SosAlertUpdate(BaseModel):
    status: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _alert_to_detail(alert: SosAlert, first_name: str | None, last_name: str | None) -> SosAlertDetail:
    pilot_name: str | None = None
    if first_name is not None or last_name is not None:
        pilot_name = f"{first_name or ''} {last_name or ''}".strip() or None

    return SosAlertDetail(
        id=str(alert.id),
        pilot_id=alert.pilot_id,
        pilot_name=pilot_name,
        lat=alert.lat,
        lon=alert.lon,
        alt=alert.alt,
        message=alert.message,
        timestamp=_iso(alert.timestamp),  # type: ignore[arg-type]
        created_at=_iso(alert.created_at),  # type: ignore[arg-type]
        status=getattr(alert, "status", "active"),
        acknowledged_at=_iso(getattr(alert, "acknowledged_at", None)),
        resolved_at=_iso(getattr(alert, "resolved_at", None)),
        resolved_by=getattr(alert, "resolved_by", None),
        notes=getattr(alert, "notes", None),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/admin/sos", response_model=list[SosAlertDetail])
def list_sos_alerts(
    status_filter: Annotated[str, Query(alias="status")] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> list[SosAlertDetail]:
    """List all SOS alerts, newest first. Optionally filter by status."""
    if status_filter not in ("all", "active", "acknowledged", "resolved"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="status must be one of: all, active, acknowledged, resolved",
        )

    query = (
        select(SosAlert, Pilot.first_name, Pilot.last_name)
        .outerjoin(Pilot, SosAlert.pilot_id == Pilot.id)
        .order_by(SosAlert.timestamp.desc())
        .limit(limit)
    )

    if status_filter != "all":
        query = query.where(SosAlert.status == status_filter)

    rows = session.execute(query).all()
    return [_alert_to_detail(alert, first_name, last_name) for alert, first_name, last_name in rows]


@router.patch("/api/admin/sos/{alert_id}", response_model=SosAlertDetail)
def update_sos_alert(
    alert_id: str,
    body: SosAlertUpdate,
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> SosAlertDetail:
    """Update an SOS alert's status and/or notes."""
    alert = session.scalar(select(SosAlert).where(SosAlert.id == alert_id))
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SOS alert not found")

    if body.status is not None:
        if body.status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="status must be one of: acknowledged, resolved",
            )
        now = datetime.now(UTC)
        alert.status = body.status
        if body.status == "acknowledged" and alert.acknowledged_at is None:
            alert.acknowledged_at = now
        elif body.status == "resolved":
            if alert.resolved_at is None:
                alert.resolved_at = now
            alert.resolved_by = user.username

    if body.notes is not None:
        alert.notes = body.notes

    session.flush()

    # Re-query to get pilot name for the response
    row = session.execute(
        select(SosAlert, Pilot.first_name, Pilot.last_name)
        .outerjoin(Pilot, SosAlert.pilot_id == Pilot.id)
        .where(SosAlert.id == alert_id)
    ).one()

    return _alert_to_detail(row[0], row[1], row[2])


@router.delete("/api/admin/sos/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sos_alert(
    alert_id: str,
    user: User = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    """Permanently delete an SOS alert."""
    alert = session.scalar(select(SosAlert).where(SosAlert.id == alert_id))
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SOS alert not found")

    session.delete(alert)
    session.flush()
