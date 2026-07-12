from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.common import UUIDTimestampMixin


class User(UUIDTimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_single_superuser",
            "role",
            unique=True,
            postgresql_where=text("role = 'superuser'"),
            sqlite_where=text("role = 'superuser'"),
        ),
    )

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    display_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="user", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
