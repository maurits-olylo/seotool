from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Timestamped


class QueueDeadLetterRead(Timestamped):
    website_id: UUID | None
    queue_name: str
    original_job_id: str
    job_type: str
    status: str
    attempt_count: int
    failed_at: datetime
    error_message: str
    payload: dict[str, object]
    resolved_at: datetime | None
    resolution: str | None


class QueueDeadLetterResolution(BaseModel):
    resolution: str


class SecurityIncidentRead(Timestamped):
    fingerprint: str
    rule_id: str
    severity: str
    status: str
    title: str
    summary: str
    first_detected_at: datetime
    last_detected_at: datetime
    occurrence_count: int
    source_hash: str | None
    actor_user_id: UUID | None
    client_id: UUID | None
    evidence: dict[str, object]
    resolved_at: datetime | None
    resolution: str | None


class SecurityIncidentResolution(BaseModel):
    resolution: str = Field(min_length=10, max_length=2000)
