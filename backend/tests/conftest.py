import os
import tempfile

# Point settings at a throwaway data folder before any app module is imported.
os.environ["PT_DATA_DIR"] = tempfile.mkdtemp(prefix="pt-test-")
os.environ["PT_BASE_CURRENCY"] = "USD"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app, run_migrations  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    run_migrations()  # exercises the real migrations
    yield


@pytest.fixture()
def client(monkeypatch):
    # No network in tests: FX refresh becomes a no-op.
    monkeypatch.setattr("app.providers.fx_frankfurter.fetch", lambda *a, **k: [])
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with TestClient(app) as c:
        yield c
