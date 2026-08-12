import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.system import SecurityIncident
from app.models.user import SecurityAuditEvent


@dataclass(frozen=True)
class IncidentRule:
    rule_id: str
    event_type: str
    result: str
    threshold: int
    window: timedelta
    severity: str
    title: str


RULES = (
    IncidentRule(
        "repeated_login_failures",
        "authentication.login",
        "failed",
        5,
        timedelta(minutes=15),
        "high",
        "Herhaalde mislukte inlogpogingen",
    ),
    IncidentRule(
        "repeated_mfa_failures",
        "authentication.mfa",
        "failed",
        3,
        timedelta(minutes=15),
        "high",
        "Herhaalde mislukte MFA-verificaties",
    ),
    IncidentRule(
        "administrator_role_change",
        "membership.role_changed",
        "succeeded",
        1,
        timedelta(minutes=1),
        "medium",
        "Beheerdersrol gewijzigd",
    ),
)


def _fingerprint(rule: IncidentRule, event: SecurityAuditEvent) -> str:
    subject = event.source_hash or str(event.actor_user_id or event.target_id or "unknown")
    occurred_at = event.occurred_at
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    bucket = occurred_at.astimezone(UTC).strftime("%Y-%m-%d")
    return hashlib.sha256(f"{rule.rule_id}:{subject}:{bucket}".encode()).hexdigest()


def detect_security_incidents(
    db: Session, *, event: SecurityAuditEvent | None = None
) -> list[SecurityIncident]:
    now = event.occurred_at if event else datetime.now(UTC)
    detected: list[SecurityIncident] = []
    detected_ids: set[str] = set()
    for rule in RULES:
        if event and (event.event_type != rule.event_type or event.result != rule.result):
            continue
        candidates = [event] if event else list(
            db.scalars(
                select(SecurityAuditEvent).where(
                    SecurityAuditEvent.event_type == rule.event_type,
                    SecurityAuditEvent.result == rule.result,
                    SecurityAuditEvent.occurred_at >= now - rule.window,
                )
            )
        )
        for candidate in candidates:
            if candidate is None:
                continue
            if rule.rule_id == "administrator_role_change" and (
                candidate.details or {}
            ).get("new_role") != "admin":
                continue
            filters = [
                SecurityAuditEvent.event_type == rule.event_type,
                SecurityAuditEvent.result == rule.result,
                SecurityAuditEvent.occurred_at >= candidate.occurred_at - rule.window,
                SecurityAuditEvent.occurred_at <= candidate.occurred_at,
            ]
            if candidate.source_hash:
                filters.append(SecurityAuditEvent.source_hash == candidate.source_hash)
            elif candidate.actor_user_id:
                filters.append(SecurityAuditEvent.actor_user_id == candidate.actor_user_id)
            elif candidate.target_id:
                filters.append(SecurityAuditEvent.target_id == candidate.target_id)
            count = int(db.scalar(select(func.count(SecurityAuditEvent.id)).where(*filters)) or 0)
            if count < rule.threshold:
                continue
            fingerprint = _fingerprint(rule, candidate)
            incident = db.scalar(
                select(SecurityIncident).where(SecurityIncident.fingerprint == fingerprint)
            )
            if incident is None:
                incident = SecurityIncident(
                    fingerprint=fingerprint,
                    rule_id=rule.rule_id,
                    severity=rule.severity,
                    title=rule.title,
                    summary=f"Detectieregel {rule.rule_id} bereikte de drempel.",
                    first_detected_at=candidate.occurred_at,
                    last_detected_at=candidate.occurred_at,
                    occurrence_count=count,
                    source_hash=candidate.source_hash,
                    actor_user_id=candidate.actor_user_id,
                    client_id=candidate.client_id,
                    evidence={
                        "event_type": rule.event_type,
                        "window_seconds": int(rule.window.total_seconds()),
                        "threshold": rule.threshold,
                    },
                )
                db.add(incident)
            else:
                incident.last_detected_at = candidate.occurred_at
                incident.occurrence_count = max(incident.occurrence_count, count)
                if incident.status == "resolved":
                    incident.status = "reopened"
                    incident.resolved_at = None
                    incident.resolution = None
            identity = incident.fingerprint
            if identity not in detected_ids:
                detected.append(incident)
                detected_ids.add(identity)
    return detected


def resolve_security_incident(
    incident: SecurityIncident, resolution: str
) -> None:
    if incident.status not in {"open", "reopened", "investigating"}:
        raise ValueError("Dit securityincident is al afgehandeld.")
    incident.status = "resolved"
    incident.resolved_at = datetime.now(UTC)
    incident.resolution = resolution.strip()
