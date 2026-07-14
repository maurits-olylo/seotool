import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["API_KEY"] = "test-key"
os.environ["APP_ENV"] = "test"

import pytest

import app.models  # noqa: F401  # Register all tables without importing the FastAPI app.
from app.db.base import Base
from app.db.session import engine


@pytest.fixture(autouse=True)
def database(request):  # type: ignore[no-untyped-def]
    requires_database = "client" in request.fixturenames or hasattr(request.module, "SessionLocal")
    if not requires_database:
        yield
        return
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():  # type: ignore[no-untyped-def]
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, headers={"X-API-Key": "test-key"})
