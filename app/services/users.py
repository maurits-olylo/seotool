import structlog
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

logger = structlog.get_logger()


def ensure_initial_superuser() -> None:
    settings = get_settings()
    if not settings.initial_superuser_email or not settings.initial_superuser_password:
        logger.warning("initial_superuser_not_configured")
        return
    email = settings.initial_superuser_email.strip().lower()
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            return
        db.add(
            User(
                email=email,
                display_name="Beheerder",
                role="superuser",
                password_hash=hash_password(settings.initial_superuser_password),
            )
        )
        db.commit()
        logger.info("initial_superuser_created", email=email)
