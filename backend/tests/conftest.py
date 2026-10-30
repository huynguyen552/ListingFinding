import os
import tempfile
from pathlib import Path

_temp = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "sqlite:///" + (Path(_temp.name) / "test.db").as_posix()
)
if not os.environ["DATABASE_URL"].startswith("sqlite") and not os.environ["DATABASE_URL"].endswith(
    "_test"
):
    raise RuntimeError("Tests require a database name ending in _test.")

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import CrawlControl, Source


@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    yield
    engine.dispose()
    _temp.cleanup()


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add_all(
            [
                CrawlControl(id=1),
                Source(
                    id="google_maps",
                    name="Maps",
                    allow_store=True,
                    allow_display=True,
                    allow_export=True,
                ),
                Source(
                    id="website",
                    name="Website",
                    allow_store=True,
                    allow_display=True,
                    allow_export=True,
                ),
                Source(
                    id="csv", name="CSV", allow_store=True, allow_display=True, allow_export=True
                ),
                Source(
                    id="manual",
                    name="Manual",
                    allow_store=True,
                    allow_display=True,
                    allow_export=True,
                ),
            ]
        )
        db.commit()
    with TestClient(app) as client:
        yield client


@pytest.fixture()
def auth(client):
    response = client.post(
        "/api/v1/setup", json={"username": "tester", "password": "TestPasswordOnly123!"}
    )
    assert response.status_code == 201
    client.headers["X-CSRF-Token"] = response.json()["csrf"]
    return client
