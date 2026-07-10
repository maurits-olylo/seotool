from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel, Timestamped


class UrlRead(ORMModel):
    id: UUID
    website_id: UUID
    normalized_url: str
    first_seen_at: datetime
    last_seen_at: datetime
    current_status_code: int | None
    is_active: bool
    crawl_depth: int | None


class UrlRegister(BaseModel):
    url: str
    source_type: Literal["sitemap", "internal_link", "known", "manual"] = "manual"
    source_url: str = ""


class CrawlJobCreate(BaseModel):
    website_id: UUID
    job_type: Literal["fetch_sitemap", "light_check", "full_page_analysis", "full_site_crawl"]
    settings_snapshot: dict[str, object] = Field(default_factory=dict)


class CrawlJobRead(Timestamped):
    website_id: UUID
    job_type: str
    status: str
    scheduled_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    attempt_count: int
    error_message: str | None
    settings_snapshot: dict[str, object]
