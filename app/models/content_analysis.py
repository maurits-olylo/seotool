import uuid
from datetime import date

from sqlalchemy import JSON, Boolean, Date, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class ContentAnalysisSettings(Base):
    __tablename__ = "content_analysis_settings"

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), primary_key=True
    )
    branded_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    sector_template: Mapped[str | None] = mapped_column(String(80))


class UrlContentClassification(UUIDTimestampMixin, Base):
    __tablename__ = "url_content_classifications"
    __table_args__ = (
        UniqueConstraint(
            "url_id",
            "input_hash",
            "classification_version",
            name="uq_url_content_classification_input_version",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    input_hash: Mapped[str] = mapped_column(String(64))
    classification_version: Mapped[str] = mapped_column(String(40))
    search_intent: Mapped[str] = mapped_column(String(40), index=True)
    journey_stage: Mapped[str] = mapped_column(String(40), index=True)
    content_role: Mapped[str] = mapped_column(String(40), index=True)
    confidence: Mapped[float] = mapped_column(Float)
    probabilities: Mapped[dict[str, float]] = mapped_column(JSON)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)


class UrlContentOverride(UUIDTimestampMixin, Base):
    __tablename__ = "url_content_overrides"
    __table_args__ = (UniqueConstraint("url_id", name="uq_url_content_overrides_url"),)

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    url_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("urls.id", ondelete="CASCADE"), index=True)
    search_intent: Mapped[str | None] = mapped_column(String(40))
    journey_stage: Mapped[str | None] = mapped_column(String(40))
    content_role: Mapped[str | None] = mapped_column(String(40))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True)
    rationale: Mapped[str | None] = mapped_column(Text)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class QueryContentClassification(UUIDTimestampMixin, Base):
    __tablename__ = "query_content_classifications"
    __table_args__ = (
        UniqueConstraint(
            "normalized_query",
            "language",
            "country",
            "classification_version",
            name="uq_query_content_classification_context_version",
        ),
    )

    normalized_query: Mapped[str] = mapped_column(String(2048))
    language: Mapped[str] = mapped_column(String(10))
    country: Mapped[str] = mapped_column(String(2))
    classification_version: Mapped[str] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64))
    search_intent: Mapped[str] = mapped_column(String(40), index=True)
    journey_stage: Mapped[str] = mapped_column(String(40))
    content_role: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    probabilities: Mapped[dict[str, float]] = mapped_column(JSON)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
