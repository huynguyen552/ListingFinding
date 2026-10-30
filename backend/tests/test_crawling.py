import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.crawl_network import FetchError, public_target
from app.crawling import StopCrawl, in_area, place_key, save_place, tick
from app.db import SessionLocal
from app.extraction import extract_website
from app.models import CrawlControl, CrawlEntry, CrawlJob, Location, Observation


def start(auth, monkeypatch, **kwargs):
    monkeypatch.setattr("app.worker.crawl.apply_async", lambda *a, **k: None)
    return auth.post(
        "/api/v1/crawl-jobs",
        json={
            "keyword": "quán ăn",
            "area": "Đà Nẵng",
            "target": 2,
            "request_key": str(uuid.uuid4()),
            **kwargs,
        },
    )


def test_job_creation_control_and_idempotency(auth, monkeypatch):
    key = str(uuid.uuid4())
    first = start(auth, monkeypatch, request_key=key)
    assert first.status_code == 202, first.text
    job_id = first.json()["id"]
    assert start(auth, monkeypatch, request_key=key).json()["id"] == job_id
    assert start(auth, monkeypatch).status_code == 409
    assert auth.post(f"/api/v1/crawl-jobs/{job_id}/pause").json()["status"] == "paused"
    assert auth.post(f"/api/v1/crawl-jobs/{job_id}/resume").json()["status"] == "queued"
    assert auth.post(f"/api/v1/crawl-jobs/{job_id}/cancel").json()["status"] == "cancelled"
    assert auth.post(f"/api/v1/crawl-jobs/{job_id}/resume").status_code == 409
    assert start(auth, monkeypatch, target=201).status_code == 422


def test_save_source_provenance_resume_and_no_overwrite(auth, monkeypatch):
    response = start(auth, monkeypatch)
    job_id = response.json()["id"]
    url = "https://www.google.com/maps/place/Test/data=!4m7!1s0x123:0xabc!8m2?hl=vi"
    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        job.status, job.run_token = "running", "test-token"
        entry = CrawlEntry(job_id=job_id, external_key=place_key(url), url=url, name="Quán A")
        db.add(entry)
        db.commit()
        entry_id = entry.id
    values = {
        "name": "Quán A",
        "address": "1 Đường A, Đà Nẵng",
        "city": "Đà Nẵng",
        "category": "quán ăn",
        "phone": "0900000000",
        "website": "https://example.com",
    }
    save_place(
        job_id,
        "test-token",
        entry_id,
        values,
        [("tax_code", "0012345678", "https://example.com/contact")],
    )
    save_place(job_id, "test-token", entry_id, {**values, "phone": "0911111111"})
    with SessionLocal() as db:
        rows = db.scalars(select(Location)).all()
        assert len(rows) == 1 and rows[0].phone == "0900000000"
        assert rows[0].tax_code == "0012345678" and rows[0].tax_status == "unverified"
        assert rows[0].provenance["tax_code"] == "website"
        assert len(db.scalars(select(Observation).where(Observation.field == "phone")).all()) == 2
    detail = auth.get(f"/api/v1/crawl-jobs/{job_id}").json()
    assert detail["counts"]["done"] == 1
    assert detail["entries"][0]["source_url"] == "https://www.google.com/maps?cid=2748"
    assert "0012345678" in auth.get(
        f"/api/v1/exports/download?format=csv&crawl_job_id={job_id}&include_unverified_tax=true"
    ).content.decode("utf-8-sig")
    assert auth.get("/api/v1/exports/download?format=csv&crawl_job_id=missing").status_code == 404
    with SessionLocal() as db:
        db.get(CrawlJob, job_id).status = "pausing"
        db.commit()
    with pytest.raises(StopCrawl):
        tick(job_id, "test-token")
    with pytest.raises(StopCrawl):
        save_place(job_id, "old-token", entry_id, values)


def test_website_extraction_uses_labeled_tax_code():
    html = """<a href="tel:0900000000">Gọi</a><a href="mailto:info@example.com">Mail</a><a href="/lien-he">Liên hệ</a><footer>Mã số thuế: 0012345678-001</footer>"""
    values, links = extract_website(html, "https://example.com")
    assert values["tax_code"] == "0012345678001"
    assert values["phone"] == "0900000000"
    assert links == ["https://example.com/lien-he"]
    assert (
        "tax_code" not in extract_website("<p>Điện thoại 0901234567</p>", "https://example.com")[0]
    )


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fc00::1"])
def test_network_blocks_internal_dns(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(0, 0, 0, "", (ip, 443))])
    with pytest.raises(FetchError):
        public_target("https://restaurant.example")


def test_area_and_stable_place_identity():
    assert in_area("26 Tô Hiến Thành, An Hải, Đà Nẵng", "Đà Nẵng")
    assert not in_area("96 Thạch Thị Thanh, TP Hồ Chí Minh", "Đà Nẵng")
    assert in_area("An Hải, Đà Nẵng", "An Hải, Đà Nẵng")
    assert place_key(
        "https://www.google.com/maps/place/A/data=!1s0x123:0xabc!8m2?x=1"
    ) == place_key("https://www.google.com/maps/place/B/data=!1s0x123:0xabc!8m2?x=2")


def test_dispatch_recovers_stale_work(auth, monkeypatch):
    from app.worker import dispatch

    created = start(auth, monkeypatch).json()
    with SessionLocal() as db:
        job = db.get(CrawlJob, created["id"])
        job.status = "running"
        job.run_token = "old"
        job.heartbeat = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        db.commit()
    dispatch.run()
    with SessionLocal() as db:
        assert db.get(CrawlJob, created["id"]).status == "paused"
        assert db.get(CrawlControl, 1).active_job_id is None
