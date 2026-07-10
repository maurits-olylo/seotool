from datetime import datetime
from uuid import UUID

from app.schemas.common import ORMModel


class CrawlRunRead(ORMModel):
    id: UUID
    crawl_job_id: UUID
    website_id: UUID
    crawl_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    discovered_urls: int
    crawled_urls: int
    failed_urls: int


class UrlSnapshotRead(ORMModel):
    id: UUID
    url_id: UUID
    crawl_run_id: UUID
    checked_at: datetime
    requested_url: str
    final_url: str | None
    status_code: int | None
    redirect_chain: list[dict[str, object]]
    content_type: str | None
    response_time_ms: int | None
    response_size: int | None
    title: str | None
    meta_description: str | None
    canonical: str | None
    meta_robots: str | None
    x_robots_tag: str | None
    html_lang: str | None
    headings: dict[str, list[str]]
    word_count: int | None
    schema_types: list[str]
    html_hash: str | None
    main_content_hash: str | None
    metadata_hash: str | None
    links_hash: str | None
    schema_hash: str | None
    is_indexable: bool | None
    error_message: str | None
