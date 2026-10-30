import importlib.util
from pathlib import Path

import pytest

from app.bootstrap import bootstrap_admin
from app.db import SessionLocal
from app.models import User
from app.security import verify_password
from app.settings import allowed_hosts, allowed_origins, database_url


@pytest.mark.parametrize("prefix", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_render_database_url_keeps_credentials_and_parameters(prefix):
    suffix = "user:p%40ss@database.internal/leadfinder?sslmode=require"
    assert database_url(prefix + suffix) == "postgresql+psycopg://" + suffix


def test_render_hostname_and_origin_are_explicit(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_HOSTNAME", "leadfinder-example.onrender.com")
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://leadfinder-example.onrender.com")
    assert "leadfinder-example.onrender.com" in allowed_hosts()
    assert "https://leadfinder-example.onrender.com" in allowed_origins()
    assert "*" not in allowed_hosts()
    assert "https://other.onrender.com" not in allowed_origins()


def test_bootstrap_requires_credentials_before_public_start(client, monkeypatch):
    monkeypatch.delenv("INITIAL_ADMIN_USERNAME", raising=False)
    monkeypatch.delenv("INITIAL_ADMIN_PASSWORD", raising=False)
    with SessionLocal() as db, pytest.raises(RuntimeError, match="INITIAL_ADMIN"):
        bootstrap_admin(db)


def test_bootstrap_does_not_reset_existing_password(client, monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_USERNAME", "company-admin")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "OnlyForTest123456!")
    with SessionLocal() as db:
        assert bootstrap_admin(db)
        assert verify_password("OnlyForTest123456!", db.get(User, 1).password_hash)
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "ChangedEnvironment123!")
    with SessionLocal() as db:
        assert not bootstrap_admin(db)
        assert verify_password("OnlyForTest123456!", db.get(User, 1).password_hash)


def test_cloud_session_cookie_is_secure(client, monkeypatch):
    monkeypatch.setenv("SECURE_COOKIES", "1")
    response = client.post(
        "/api/v1/setup", json={"username": "tester", "password": "OnlyForTest123456!"}
    )
    assert response.status_code == 201
    assert "Secure" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_cloud_runtime_starts_one_crawler_with_dynamic_port(monkeypatch):
    monkeypatch.delenv("QUEUE_MODE", raising=False)
    path = Path(__file__).resolve().parents[2] / "deploy" / "render_runtime.py"
    if not path.exists():
        pytest.skip("The local backend-only image does not include Render runtime.")
    spec = importlib.util.spec_from_file_location("render_runtime", path)
    runtime = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime)
    commands = dict(runtime.process_commands(12345))
    assert "12345" in commands["web"]
    assert "--pool=solo" in commands["crawler"]
    assert "--concurrency=1" in commands["crawler"]
    assert "127.0.0.1" in commands["redis"]
    monkeypatch.setenv("QUEUE_MODE", "database")
    commands = dict(runtime.process_commands(12345))
    assert set(commands) == {"crawler", "web"}
    assert "app.render_worker" in commands["crawler"]


def test_database_queue_does_not_publish_to_redis(auth, monkeypatch):
    import uuid

    from app.queueing import collect_work

    monkeypatch.setenv("QUEUE_MODE", "database")

    published = []
    monkeypatch.setattr("app.worker.crawl.apply_async", lambda *a, **k: published.append(a))
    response = auth.post(
        "/api/v1/crawl-jobs",
        json={
            "keyword": "quán ăn",
            "area": "Đà Nẵng",
            "target": 1,
            "request_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 202
    assert published == []
    assert collect_work() == [response.json()["id"]]


def test_database_worker_stops_at_checkpoint(monkeypatch):
    from app.crawling import StopCrawl, tick
    from app.queueing import shutdown_requested

    monkeypatch.setenv("QUEUE_MODE", "database")
    shutdown_requested.set()
    try:
        with pytest.raises(StopCrawl):
            tick("not-a-real-job", "old")
    finally:
        shutdown_requested.clear()
