import uuid

import pytest

from app import crawling
from app.db import SessionLocal
from app.models import CrawlEntry, CrawlJob

VALUES = {
    "name": "Quán thử",
    "address": "12 Đường A, Đà Nẵng",
    "phone": "0901234567",
    "website": "",
    "category": "Quán ăn",
}


def job_with_entry(cached, *, area="Đà Nẵng", enrich=False, values=None):
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area=area,
            target=1,
            enrich_website=enrich,
            status="queued",
            discovery_complete=True,
        )
        db.add(job)
        db.flush()
        db.add(
            CrawlEntry(
                job_id=job.id,
                external_key=str(uuid.uuid4()),
                url="https://www.google.com/maps/place/fixture",
                raw_data={
                    "values": dict(values or VALUES),
                    "collected_at": "2026-10-30T00:00:00+00:00",
                }
                if cached
                else None,
            )
        )
        db.commit()
        return job.id


@pytest.mark.parametrize("area,expected", [("Đà Nẵng", "completed"), ("Hà Nội", "no_results")])
def test_cached_area_recheck_never_starts_browser(auth, monkeypatch, area, expected):
    started = []

    def fail_start():
        started.append(True)
        raise AssertionError("No browser needed for cached details")

    monkeypatch.setattr(crawling, "sync_playwright", fail_start)
    monkeypatch.setattr(crawling.time, "sleep", lambda *a: None)
    job_id = job_with_entry(True, area=area)
    crawling.run_crawl(job_id)
    with SessionLocal() as db:
        assert db.get(CrawlJob, job_id).status == expected
    assert started == []


def fake_browser(monkeypatch):
    events = []

    class Page:
        def set_default_timeout(self, timeout):
            pass

    class Context:
        def route(self, *a):
            pass

        def new_page(self):
            return Page()

    class Browser:
        def new_context(self, **kw):
            return Context()

        def is_connected(self):
            return True

        def close(self):
            events.append("close")

    class Playwright:
        @property
        def chromium(self):
            return self

        def launch(self, **kw):
            events.append("launch")
            return Browser()

        def stop(self):
            events.append("stop")

    class Factory:
        def start(self):
            events.append("start")
            return Playwright()

    monkeypatch.setattr(crawling, "sync_playwright", Factory)
    return events


def test_browser_is_released_after_each_place(monkeypatch):
    events = fake_browser(monkeypatch)
    monkeypatch.setattr(crawling, "read_place", lambda *a: dict(VALUES))
    with crawling.MapBrowser() as maps:
        assert events == []
        for _ in range(2):
            assert maps.read("https://www.google.com/maps/place/fixture") == VALUES
            assert maps.browser is None and maps.playwright is None
    assert events == ["start", "launch", "close", "stop"] * 2


def test_read_failure_also_releases_browser(monkeypatch):
    events = fake_browser(monkeypatch)

    def fail(*a):
        raise ValueError("Missing address")

    monkeypatch.setattr(crawling, "read_place", fail)
    with crawling.MapBrowser() as maps, pytest.raises(ValueError):
        maps.read("https://www.google.com/maps/place/fixture")
    assert events == ["start", "launch", "close", "stop"]


def test_website_is_read_after_chromium_is_released(auth, monkeypatch):
    events = fake_browser(monkeypatch)
    values = {**VALUES, "website": "https://example.com"}
    monkeypatch.setattr(crawling, "read_place", lambda *a: dict(values))
    monkeypatch.setattr(crawling.time, "sleep", lambda *a: None)
    monkeypatch.setattr(crawling, "require_robots", lambda *a: None)

    def fetch(url, **kw):
        assert events[-2:] == ["close", "stop"]
        return 200, "<p>MST: 0012345678</p>", url

    monkeypatch.setattr(crawling, "fetch", fetch)
    job_id = job_with_entry(False, enrich=True)
    crawling.run_crawl(job_id)
    detail = auth.get(f"/api/v1/crawl-jobs/{job_id}").json()
    assert detail["status"] == "completed"
    assert detail["entries"][0]["location"]["phone"] == VALUES["phone"]
    assert detail["entries"][0]["location"]["tax_code"] == "0012345678"
