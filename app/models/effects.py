import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import utc_now


class EffectIntervention(Base):
    __tablename__ = "effect_interventions"
    __table_args__ = (
        UniqueConstraint("task_id", name="uq_effect_interventions_task"),
        UniqueConstraint(
            "website_id",
            "input_hash",
            "intervention_version",
            name="uq_effect_interventions_input_version",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    website_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("websites.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("recommendation_tasks.id", ondelete="CASCADE"), index=True
    )
    implemented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    intervention_version: Mapped[str] = mapped_column(String(30))
    input_hash: Mapped[str] = mapped_column(String(64))
    task_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    url_context: Mapped[list[dict[str, object]]] = mapped_column(JSON, default=list)
    source_coverage: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
