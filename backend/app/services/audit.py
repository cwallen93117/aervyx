from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    session: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict,
) -> None:
    session.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            details_json=details,
        )
    )