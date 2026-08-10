import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class WebsiteOnboarding(UUIDTimestampMixin, Base):
    __tablename__ = "website_onboardings"
    __table_args__ = (
        UniqueConstraint("client_id", "request_id", name="uq_website_onboarding_request"),
        UniqueConstraint("website_id", name="uq_website_onboarding_website"),
        UniqueConstraint("first_crawl_job_id", name="uq_website_onboarding_first_crawl_job"),
        CheckConstraint(
            "status IN ('verification_pending', 'verified', 'crawl_queued', 'completed', 'failed')",
            name="ck_website_onboardings_status",
        ),
        CheckConstraint(
            "current_step IN ('verification', 'crawl_preferences', 'first_crawl', 'results')",
            name="ck_website_onboardings_step",
        ),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), index=True
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    started_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    request_id: Mapped[uuid.UUID] = mapped_column(index=True)
    first_crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crawl_jobs.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="verification_pending", index=True)
    current_step: Mapped[str] = mapped_column(String(30), default="verification", index=True)
    last_error_code: Mapped[str | None] = mapped_column(String(50))
    detected_platform: Mapped[str | None] = mapped_column(String(40))
    platform_confidence: Mapped[str | None] = mapped_column(String(20))
    confirmed_platform: Mapped[str | None] = mapped_column(String(40))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebsiteOwnershipVerification(UUIDTimestampMixin, Base):
    __tablename__ = "website_ownership_verifications"
    __table_args__ = (
        UniqueConstraint("onboarding_id", name="uq_website_verification_onboarding"),
        UniqueConstraint("token_hash", name="uq_website_verification_token_hash"),
        CheckConstraint("method = 'https_file'", name="ck_website_verifications_method"),
        CheckConstraint(
            "status IN ('pending', 'verified', 'expired')",
            name="ck_website_verifications_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_website_verifications_attempts"),
    )

    onboarding_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("website_onboardings.id", ondelete="CASCADE"), index=True
    )
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(20), default="https_file")
    token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
