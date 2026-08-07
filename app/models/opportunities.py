import uuid
from datetime import date

from sqlalchemy import JSON, CheckConstraint, Date, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class OpportunityEvaluation(UUIDTimestampMixin, Base):
    __tablename__ = "opportunity_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "website_id",
            "scope_type",
            "scope_key",
            "input_hash",
            "formula_version",
            name="uq_opportunity_evaluation_input_formula",
        ),
        CheckConstraint(
            "scope_type IN ('page', 'url_family', 'shared_cause')",
            name="ck_opportunity_evaluations_scope_type",
        ),
        CheckConstraint(
            "priority_class IN ('high_opportunity', 'opportunity', 'monitor', "
            "'insufficient_evidence')",
            name="ck_opportunity_evaluations_priority_class",
        ),
        CheckConstraint(
            "potential_score IS NULL OR potential_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_potential_score",
        ),
        CheckConstraint(
            "friction_score IS NULL OR friction_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_friction_score",
        ),
        CheckConstraint(
            "evidence_score IS NULL OR evidence_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_evidence_score",
        ),
        CheckConstraint(
            "feasibility_score IS NULL OR feasibility_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_feasibility_score",
        ),
        CheckConstraint(
            "total_score IS NULL OR total_score BETWEEN 0 AND 100",
            name="ck_opportunity_evaluations_total_score",
        ),
    )

    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    primary_url_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("urls.id", ondelete="SET NULL"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(30), index=True)
    scope_key: Mapped[str] = mapped_column(String(255))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    input_hash: Mapped[str] = mapped_column(String(64))
    formula_version: Mapped[str] = mapped_column(String(50), index=True)
    potential_score: Mapped[float | None] = mapped_column(Float)
    friction_score: Mapped[float | None] = mapped_column(Float)
    evidence_score: Mapped[float | None] = mapped_column(Float)
    feasibility_score: Mapped[float | None] = mapped_column(Float)
    total_score: Mapped[float | None] = mapped_column(Float)
    priority_class: Mapped[str] = mapped_column(String(30), index=True)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    contributors: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
