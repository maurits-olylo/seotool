from unittest.mock import Mock

import pytest
from sqlalchemy import exc

from app.db import session


def test_connection_from_parent_process_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    record = Mock()
    record.info = {"pid": 100}
    record.dbapi_connection = object()
    monkeypatch.setattr(session.os, "getpid", lambda: 200)

    with pytest.raises(exc.DisconnectionError, match="another process"):
        session.reject_connection_from_parent_process(object(), record, Mock())

    assert record.dbapi_connection is None


def test_connection_from_current_process_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = object()
    record = Mock()
    record.info = {"pid": 200}
    record.dbapi_connection = connection
    monkeypatch.setattr(session.os, "getpid", lambda: 200)

    session.reject_connection_from_parent_process(object(), record, Mock())

    assert record.dbapi_connection is connection
