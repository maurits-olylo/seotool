from datetime import date
from hashlib import sha256
from unittest.mock import Mock

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.session import engine
from app.models.client import Client
from app.models.integrations import SearchConsoleMetric, SearchConsoleQueryMetric
from app.models.website import Website
from app.services.metric_storage import insert_metric_rows

SessionLocal = sessionmaker(bind=engine)


def test_metric_rows_are_inserted_in_bounded_batches() -> None:
    db = Mock()
    rows = [{"page_url": str(index)} for index in range(5)]

    insert_metric_rows(db, SearchConsoleMetric, rows, batch_size=2)

    assert db.execute.call_count == 3
    assert [len(call.args[1]) for call in db.execute.call_args_list] == [2, 2, 1]


def test_gsc_bulk_inserts_generate_stable_compact_dedup_keys() -> None:
    metric_date = date(2026, 7, 26)
    page_url = "https://example.com/a-long-page"
    with SessionLocal() as db:
        client = Client(name="GSC key client")
        db.add(client)
        db.flush()
        website = Website(
            client_id=client.id,
            name="GSC key website",
            base_url="https://example.com/",
        )
        db.add(website)
        db.flush()
        insert_metric_rows(
            db,
            SearchConsoleMetric,
            [
                {
                    "website_id": website.id,
                    "date": metric_date,
                    "page_url": page_url,
                }
            ],
        )
        insert_metric_rows(
            db,
            SearchConsoleQueryMetric,
            [
                {
                    "website_id": website.id,
                    "date": metric_date,
                    "query": "test query",
                    "page_url": page_url,
                }
            ],
        )
        db.commit()
        page_metric = db.scalar(select(SearchConsoleMetric))
        query_metric = db.scalar(select(SearchConsoleQueryMetric))

    assert page_metric is not None
    assert query_metric is not None
    assert page_metric.dedup_key == sha256(page_url.encode()).hexdigest()
    assert query_metric.dedup_key == sha256(f"test query\0{page_url}".encode()).hexdigest()
