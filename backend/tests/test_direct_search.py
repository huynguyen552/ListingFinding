"""Regression: Maps can open a place while retaining /maps/search/ in the URL."""

from sqlalchemy import select

from app.crawling import discover, place_key
from app.db import SessionLocal
from app.models import CrawlEntry, CrawlJob


class Element:
    def __init__(self, kind):
        self.kind = kind

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def count(self):
        return 1 if self.kind == "address" else 0

    def wait_for(self, **kwargs):
        return None

    def evaluate_all(self, *args):
        return []

    def inner_text(self):
        return "Quán thử"

    def get_attribute(self, name):
        return "Địa chỉ: 1 Đường A, Đà Nẵng"


class DirectSearchPage:
    url = "https://www.google.com/maps/search/quan-thu/?hl=vi"

    def goto(self, url, **kwargs):
        self.url = url

    def get_by_role(self, role):
        return Element("feed")

    def locator(self, selector):
        return Element("address" if selector == '[data-item-id="address"]' else selector)

    def evaluate(self, script):
        return {
            "name": "Quán thử",
            "address": "1 Đường A, Đà Nẵng",
            "phone": "0901234567",
            "website": "https://example.com/",
            "category": "Quán ăn",
        }


def test_direct_search_result_is_not_discarded(auth):
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key="direct-search-regression",
            keyword="quán thử",
            area="Đà Nẵng",
            target=1,
            status="running",
            run_token="regression-token",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    discover(DirectSearchPage(), job_id, "regression-token", "quán thử", "Đà Nẵng", 1)
    with SessionLocal() as db:
        rows = db.scalars(select(CrawlEntry).where(CrawlEntry.job_id == job_id)).all()
        assert len(rows) == 1
        assert "/maps/search/" in rows[0].url
        assert rows[0].name == "Quán thử"
        assert rows[0].raw_data["values"]["phone"] == "0901234567"
        assert rows[0].raw_data["values"]["website"] == "https://example.com"
        assert db.get(CrawlJob, job_id).discovery_complete


def test_resume_discovery_scrolls_past_already_saved_candidates(auth, monkeypatch):
    monkeypatch.setattr("app.crawling.time.sleep", lambda *a: None)
    urls = [f"https://www.google.com/maps/place/fixture/data=!1splace-{i}!8m2" for i in range(8)]

    class Feed(Element):
        def count(self):
            return 1

        def evaluate(self, script):
            page.index += 1

    class Links(Element):
        def evaluate_all(self, script):
            return [{"url": urls[page.index], "name": "Quán thử"}] if page.index < len(urls) else []

    class FeedPage(DirectSearchPage):
        index = 0

        def get_by_role(self, role):
            return Feed("feed")

        def locator(self, selector):
            if selector == 'a[href*="/maps/place/"]':
                return Links("links")
            return super().locator(selector)

    page = FeedPage()
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key="resume-discovery-regression",
            keyword="quán ăn",
            area="Đà Nẵng",
            target=3,
            status="running",
            run_token="token",
        )
        db.add(job)
        db.flush()
        for url in urls[:4]:
            db.add(CrawlEntry(job_id=job.id, external_key=place_key(url), url=url))
        db.commit()
        job_id = job.id
    discover(page, job_id, "token", "quán ăn", "Đà Nẵng", 3)
    with SessionLocal() as db:
        assert len(db.scalars(select(CrawlEntry).where(CrawlEntry.job_id == job_id)).all()) == 8
