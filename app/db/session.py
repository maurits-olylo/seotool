import os
from typing import Any

from sqlalchemy import create_engine, event, exc
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings

database_url = get_settings().database_url
engine_options: dict[str, object] = {"pool_pre_ping": True}
if database_url == "sqlite+pysqlite:///:memory:":
    engine_options.update({"connect_args": {"check_same_thread": False}, "poolclass": StaticPool})
engine = create_engine(database_url, **engine_options)


@event.listens_for(engine, "connect")
def record_connection_process_id(_connection: object, connection_record: Any) -> None:
    connection_record.info["pid"] = os.getpid()


@event.listens_for(engine, "checkout")
def reject_connection_from_parent_process(
    _connection: object,
    connection_record: Any,
    _connection_proxy: Any,
) -> None:
    if connection_record.info.get("pid") == os.getpid():
        return
    connection_record.dbapi_connection = None
    raise exc.DisconnectionError(
        "Database connection belongs to another process; reconnecting safely"
    )


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_db():  # type: ignore[no-untyped-def]
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
