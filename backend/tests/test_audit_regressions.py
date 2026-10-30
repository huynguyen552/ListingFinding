"""Cases uncovered by the collection-flow audit, beyond individual street fixes."""

import uuid

import pytest

from app.area_matching import AreaMatcher, text_matches
from app.db import SessionLocal
from app.extraction import extract_website
from app.models import CrawlEntry, CrawlJob


@pytest.mark.parametrize(
    "area,address,expected",
    [
        ("Lê Trọng Tấn, Hồ Chí Minh", "228 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh", True),
        ("Lê Trọng Tấn, Hồ Chí Minh", "45 Đường S9, Tây Thạnh, Hồ Chí Minh", False),
        ("đường số 7, Đà Nẵng", "12 Đường Số 70, Đà Nẵng", False),
        ("Đường Nguyễn Văn Linh, Đà Nẵng", "12 Nguyễn Văn Linh Nối Dài, Đà Nẵng", False),
        ("Đường Nguyễn Văn Linh, Đà Nẵng", "12 Hẻm Nguyễn Văn Linh, Đà Nẵng", True),
        ("Đ. Lê Trọng Tấn; P. Tây Thạnh; TP.HCM", "228 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh", True),
        (
            "đường Lê Trọng Tấn phường Tây Thạnh TP.HCM",
            "228 Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh",
            True,
        ),
        ("phường An Hải, Đà Nẵng", "12 Đường A, An Hải Bắc, Đà Nẵng", False),
        ("phường Tân Hưng, TP.HCM", "12 Đường A, Tân Hưng Thuận, Hồ Chí Minh", False),
        ("phường Tây Thạnh, TP.HCM", "12 Đường Tây Thạnh, Tân Sơn Nhì, Hồ Chí Minh", False),
        ("quận Bình Thạnh, TP.HCM", "12 Đường A, Phường Bình Thạnh, Hồ Chí Minh", False),
        ("quận Bình Thạnh, TP.HCM", "12 Đường A, Quận Bình Thạnh, Hồ Chí Minh", True),
        ("Q. Bình Thạnh, TP.HCM", "12 Đường A, Quận Bình Thạnh, Hồ Chí Minh", True),
        ("phường Tây Thạnh, Hồ Chí Minh", "12 Đường A, Tây Thạnh 700000, Hồ Chí Minh", True),
        ("Đường 3/2, TP.HCM", "12 Đường 3/2, Phường A, Hồ Chí Minh", True),
        ("Đường 3/2, TP.HCM", "3/2 Đường Khác, Phường A, Hồ Chí Minh", False),
        ("Đường Lê Trọng Tấn, TP.HCM", "228, Lê Trọng Tấn, Tây Thạnh, Hồ Chí Minh", True),
        ("Phường 7, Đà Nẵng", "12 Đường A, Phường 17, Đà Nẵng", False),
        ("Q7, TP.HCM", "12 Đường Q7, Bình Thạnh, Hồ Chí Minh", False),
        ("Đường Dương Đức Hiền, TP.HCM", "14A Dương Đức Hiền, Tây Thạnh, Hồ Chí Minh", True),
        ("Dương Đức Hiền, TP.HCM", "14A Dương Đức Hiền, Tây Thạnh, Hồ Chí Minh", True),
        ("Đường Đức Hiền, TP.HCM", "14A Dương Đức Hiền, Tây Thạnh, Hồ Chí Minh", False),
        ("Đường Dương Quảng Hàm, TP.HCM", "Số 12 Dương Quảng Hàm, Phường A, Hồ Chí Minh", True),
    ],
)
def test_area_matrix(area, address, expected):
    assert text_matches(address, area) is expected
    assert AreaMatcher(area).matches(address) is expected


def test_city_is_not_entire_search_area():
    assert AreaMatcher("Đường A, An Hải, Đà Nẵng").city_label == "Đà Nẵng"
    assert AreaMatcher("Đường Hồ Chí Minh, Đà Nẵng, Việt Nam").city_label == "Đà Nẵng"
    assert AreaMatcher("Quận 7, TP.HCM").city_for("12 Đường A, Tân Hưng") == "Hồ Chí Minh"
    assert (
        AreaMatcher("An Hải, Đà Nẵng").city_for("12 Đường A, An Hải, Đà Nẵng 550000, Việt Nam")
        == "Đà Nẵng"
    )


def test_road_named_like_known_ward_does_not_activate_ward_boundary():
    assert AreaMatcher("Tân Thuận, Hồ Chí Minh").matches(
        "12 Đường Tân Thuận, Phú Thuận, Hồ Chí Minh",
        "https://www.google.com/maps/data=!3d10.7168342!4d106.7369913",
    )


@pytest.mark.parametrize("area", [",,", "; ;", "---"])
def test_empty_normalized_area_is_rejected(auth, monkeypatch, area):
    monkeypatch.setattr("app.worker.crawl.apply_async", lambda *a, **k: None)
    response = auth.post(
        "/api/v1/crawl-jobs",
        json={"keyword": "quán ăn", "area": area, "target": 1, "request_key": str(uuid.uuid4())},
    )
    assert response.status_code == 422


def test_all_failed_can_resume_and_has_error_status(auth, monkeypatch):
    monkeypatch.setattr("app.worker.crawl.apply_async", lambda *a, **k: None)
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area="Đà Nẵng",
            target=1,
            status="no_results",
            discovery_complete=True,
        )
        db.add(job)
        db.flush()
        db.add(
            CrawlEntry(
                job_id=job.id,
                external_key="failed",
                url="https://www.google.com/maps/place/a",
                state="failed",
                error="Hết thời gian đọc địa điểm.",
            )
        )
        db.commit()
        job_id = job.id
    assert auth.get(f"/api/v1/crawl-jobs/{job_id}").json()["status"] == "completed_with_errors"
    response = auth.post(f"/api/v1/crawl-jobs/{job_id}/resume")
    assert response.status_code == 200
    assert response.json()["counts"] == {"pending": 1}


def test_malformed_contact_link_does_not_discard_valid_data():
    html = '<p>MST: 0012345678</p><a href="https://[broken">Liên hệ</a>'
    values, links = extract_website(html, "https://example.com")
    assert values["tax_code"] == "0012345678"
    assert links == []


def test_tax_code_cannot_truncate_invalid_length():
    for code in ("00123456789", "001234567890", "0012345678-0012"):
        assert "tax_code" not in extract_website(f"<p>MST: {code}</p>", "https://example.com")[0]


def test_warning_is_saved_and_duplicate_alias_does_not_inflate_target(auth):
    from app.crawl_stats import crawl_counts
    from app.crawling import save_place

    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area="Đà Nẵng",
            target=2,
            status="running",
            run_token="current",
        )
        db.add(job)
        db.flush()
        entries = [
            CrawlEntry(
                job_id=job.id, external_key=k, url="https://www.google.com/maps/place/fixture"
            )
            for k in ("alias-a", "alias-b")
        ]
        db.add_all(entries)
        db.commit()
        job_id = job.id
        entry_ids = [entry.id for entry in entries]
    values = {
        "name": "Quán thử",
        "address": "1 Đường A, Đà Nẵng",
        "city": "Đà Nẵng",
        "phone": "0901234567",
        "website": "https://example.com",
    }
    for entry_id in entry_ids:
        save_place(
            job_id, "current", entry_id, values, website_error="Website không truy cập được."
        )
    detail = auth.get(f"/api/v1/crawl-jobs/{job_id}").json()
    assert detail["counts"] == {"done": 1}
    assert detail["found"] == 2 and detail["warnings"] == 2
    assert all(
        e["location"]["phone"] == "0901234567" and e["state"] == "done" for e in detail["entries"]
    )
    with SessionLocal() as db:
        assert crawl_counts(db, job_id)[0]["done"] == 1


def test_revoked_worker_cannot_mark_entry_failed(auth):
    from app.crawling import StopCrawl, record_entry_error

    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area="Đà Nẵng",
            target=1,
            status="running",
            run_token="new-token",
        )
        db.add(job)
        db.flush()
        entry = CrawlEntry(
            job_id=job.id, external_key="a", url="https://www.google.com/maps/place/a"
        )
        db.add(entry)
        db.commit()
        job_id, entry_id = job.id, entry.id
    with pytest.raises(StopCrawl):
        record_entry_error(job_id, "old-token", entry_id, "failed", "stale error")
    with SessionLocal() as db:
        assert db.get(CrawlEntry, entry_id).state == "pending"
