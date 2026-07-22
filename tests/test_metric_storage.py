from unittest.mock import Mock

from app.models.integrations import SearchConsoleMetric
from app.services.metric_storage import insert_metric_rows


def test_metric_rows_are_inserted_in_bounded_batches() -> None:
    db = Mock()
    rows = [{"page_url": str(index)} for index in range(5)]

    insert_metric_rows(db, SearchConsoleMetric, rows, batch_size=2)

    assert db.execute.call_count == 3
    assert [len(call.args[1]) for call in db.execute.call_args_list] == [2, 2, 1]
