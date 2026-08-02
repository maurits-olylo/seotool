from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

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
