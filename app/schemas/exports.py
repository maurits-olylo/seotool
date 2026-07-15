from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ExportCreate(BaseModel):
    website_id: UUID
    export_type: Literal["urls", "technical", "changes", "issues", "links", "vacancies", "excel"]
    item_ids: list[UUID] | None = Field(default=None, max_length=10_000)
    filters: dict[str, str] = Field(default_factory=dict, max_length=10)


class ExportRead(ORMModel):
    id: UUID
    website_id: UUID
    export_type: str
    status: str
    error_message: str | None
    item_ids: list[str] | None
    filters: dict[str, str]
    created_at: datetime
    finished_at: datetime | None
    downloaded_at: datetime | None
