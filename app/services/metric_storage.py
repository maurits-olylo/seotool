from typing import Any

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.db.base import Base

BULK_BATCH_SIZE = 5_000


def insert_metric_rows(
    db: Session,
    model: type[Base],
    rows: list[dict[str, Any]],
    *,
    batch_size: int = BULK_BATCH_SIZE,
) -> None:
    """Insert metric mappings without constructing one ORM object per imported row."""
    for offset in range(0, len(rows), batch_size):
        db.execute(insert(model), rows[offset : offset + batch_size])
