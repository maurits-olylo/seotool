from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ExportCreate(BaseModel):
    website_id: UUID
    export_type: Literal["urls", "technical", "changes", "issues", "links", "excel"]


class ExportRead(ORMModel):
    id: UUID
    website_id: UUID
    export_type: str
    status: str
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    downloaded_at: datetime | None
