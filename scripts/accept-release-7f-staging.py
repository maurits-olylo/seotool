#!/usr/bin/env python3
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.system import SecurityIncident
from app.models.user import SecurityAuditEvent
from app.services.security_incidents import (
    detect_security_incidents,
    resolve_security_incident,
)

SOURCE_HASH = "7f" * 32


def main() -> None:
    incident_id = None
    try:
        with SessionLocal() as db:
            now = datetime.now(UTC)
            for _attempt in range(5):
                db.add(
                    SecurityAuditEvent(
                        event_type="authentication.login",
                        result="failed",
                        source_hash=SOURCE_HASH,
                        summary="Synthetische release-7F-inlogproef",
                        occurred_at=now,
                    )
                )
            db.flush()
            detected = detect_security_incidents(db)
            assert len(detected) == 1
            incident = detected[0]
            assert incident.rule_id == "repeated_login_failures"
            assert incident.occurrence_count == 5
            db.commit()
            incident_id = incident.id

            assert len(detect_security_incidents(db)) == 1
            assert (
                len(
                    list(
                        db.scalars(
                            select(SecurityIncident).where(
                                SecurityIncident.source_hash == SOURCE_HASH
                            )
                        )
                    )
                )
                == 1
            )
            resolve_security_incident(incident, "Synthetische incidentproef afgerond.")
            db.commit()
            assert incident.status == "resolved"
            print(
                {
                    "status": "release_7f_staging_ok",
                    "rule": incident.rule_id,
                    "occurrences": incident.occurrence_count,
                    "idempotent": True,
                    "resolved": True,
                }
            )
    finally:
        with SessionLocal() as db:
            incidents = list(
                db.scalars(
                    select(SecurityIncident).where(
                        SecurityIncident.source_hash == SOURCE_HASH
                    )
                )
            )
            for incident in incidents:
                db.delete(incident)
            events = list(
                db.scalars(
                    select(SecurityAuditEvent).where(SecurityAuditEvent.source_hash == SOURCE_HASH)
                )
            )
            for event in events:
                db.delete(event)
            db.commit()
    print({"fixture_clean": True, "incident_id": str(incident_id)})


if __name__ == "__main__":
    main()
