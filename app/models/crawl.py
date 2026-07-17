import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"), unique=True, index=True
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    crawl_type: Mapped[str] = mapped_column(String(40))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    discovered_urls: Mapped[int] = mapped_column(Integer, default=0)
    crawled_urls: Mapped[int] = mapped_column(Integer, default=0)
    failed_urls: Mapped[int] = mapped_column(Integer, default=0)


class UrlSnapshot(Base):
    __tablename__ = "url_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    requested_url: Mapped[str] = mapped_column(String(2048))
    final_url: Mapped[str | None] = mapped_column(String(2048))
    status_code: Mapped[int | None] = mapped_column(Integer)
    redirect_chain: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    content_type: Mapped[str | None] = mapped_column(String(255))
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    response_size: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(512))
    last_modified: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(Text)
    meta_description: Mapped[str | None] = mapped_column(Text)
    canonical: Mapped[str | None] = mapped_column(String(2048))
    meta_robots: Mapped[str | None] = mapped_column(String(512))
    x_robots_tag: Mapped[str | None] = mapped_column(String(512))
    html_lang: Mapped[str | None] = mapped_column(String(50))
    headings: Mapped[dict[str, list[str]]] = mapped_column(JSON, default=dict)
    word_count: Mapped[int | None] = mapped_column(Integer)
    main_content: Mapped[str | None] = mapped_column(Text)
    schema_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    schema_data: Mapped[list[object]] = mapped_column(JSON, default=list)
    html_hash: Mapped[str | None] = mapped_column(String(64))
    main_content_hash: Mapped[str | None] = mapped_column(String(64))
    metadata_hash: Mapped[str | None] = mapped_column(String(64))
    links_hash: Mapped[str | None] = mapped_column(String(64))
    schema_hash: Mapped[str | None] = mapped_column(String(64))
    is_indexable: Mapped[bool | None] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)


class UrlLink(Base):
    __tablename__ = "url_links"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    source_url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    target_url: Mapped[str] = mapped_column(String(2048))
    target_url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL")
    )
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    is_internal: Mapped[bool] = mapped_column(Boolean)
    is_nofollow: Mapped[bool] = mapped_column(Boolean)
    http_status: Mapped[int | None] = mapped_column(Integer)


class ElementLocation(Base):
    __tablename__ = "element_locations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    source_url_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("urls.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("url_snapshots.id", ondelete="CASCADE"), index=True
    )
    crawl_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crawl_runs.id", ondelete="CASCADE"), index=True
    )
    issue_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    element_type: Mapped[str] = mapped_column(String(40), index=True)
    target_url: Mapped[str | None] = mapped_column(String(2048))
    visible_text: Mapped[str | None] = mapped_column(Text)
    element_id: Mapped[str | None] = mapped_column(String(512))
    css_selector: Mapped[str | None] = mapped_column(Text)
    xpath: Mapped[str | None] = mapped_column(Text)
    html_fragment: Mapped[str] = mapped_column(Text)
    occurrence_index: Mapped[int] = mapped_column(Integer, default=1)
    text_prefix: Mapped[str | None] = mapped_column(Text)
    text_suffix: Mapped[str | None] = mapped_column(Text)
    text_is_unique: Mapped[bool] = mapped_column(Boolean, default=False)
    context_is_unique: Mapped[bool] = mapped_column(Boolean, default=False)
    rendered_dynamically: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
