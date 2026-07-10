from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

database_url = get_settings().database_url
engine_options: dict[str, object] = {"pool_pre_ping": True}
if database_url == "sqlite+pysqlite:///:memory:":
    engine_options.update({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db():  # type: ignore[no-untyped-def]
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
