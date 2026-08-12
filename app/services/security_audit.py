import hashlib
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import SecurityAuditEvent
from app.services.security_incidents import detect_security_incidents


def hash_audit_source(source: str | None) -> str | None:
    if not source:
        return None
    return hashlib.sha256(source.encode()).hexdigest()


def record_security_event(
    db: Session,
    *,
    event_type: str,
    result: str,
    summary: str,
    actor_user_id: UUID | None = None,
    client_id: UUID | None = None,
    target_type: str | None = None,
    target_id: UUID | str | None = None,
    source_hash: str | None = None,
    details: dict[str, object] | None = None,
) -> SecurityAuditEvent:
    event = SecurityAuditEvent(
        actor_user_id=actor_user_id,
        client_id=client_id,
        event_type=event_type,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        result=result,
        source_hash=source_hash,
        summary=summary,
        details=details or {},
    )
    db.add(event)
    db.flush()
    detect_security_incidents(db, event=event)
    return event
