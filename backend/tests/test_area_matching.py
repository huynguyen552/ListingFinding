import uuid

import pytest
from sqlalchemy import select

from app.area_matching import AreaMatcher, canonical, in_geometry, place_coordinates, text_matches
from app.db import SessionLocal
from app.models import CrawlControl, CrawlEntry, CrawlJob


@pytest.mark.parametrize(
    "area",
    [
        "quận 7, thành phố hồ chí minh",
        "Q.7, TP.HCM",
        "District 7, Ho Chi Minh City",
        "Quận 07, HCMC",
    ],
)
def test_current_ward_address_matches_legacy_district(area):
    address = "436 Nguyễn Thị Thập, Tân Hưng, Hồ Chí Minh 72900, Việt Nam"
    assert text_matches(address, area)
    assert AreaMatcher(area).matches(
        address, "https://www.google.com/maps/place/test/data=!3d10.7393684!4d106.70807"
    )


def test_real_failed_examples_and_outside_city():
    matcher = AreaMatcher("quận 7, thành phố hồ chí minh")
    cases = [
        (
            "1 Đường Số 3 Khu Dân Cư Tân Trường, Phú Thuận, Hồ Chí Minh, Việt Nam",
            10.7334557,
            106.7393475,
        ),
        ("436 Nguyễn Thị Thập, Tân Hưng, Hồ Chí Minh 72900, Việt Nam", 10.7393684, 106.70807),
        ("469 Nguyễn Hữu Thọ, Tân Hưng, Hồ Chí Minh 008428, Việt Nam", 10.7410229, 106.702043),
    ]
    for address, lat, lon in cases:
        assert matcher.matches(
            address, f"https://www.google.com/maps/place/test/data=!3d{lat}!4d{lon}"
        )
    assert not matcher.matches(
        "Quận 7, Hồ Chí Minh", "https://www.google.com/maps/place/test/data=!3d10.777!4d106.700"
    )
    assert not text_matches("Tân Hưng, Hải Phòng, Việt Nam", "Quận 7, TP.HCM")
    assert not text_matches("12 Đường Tân Hưng, Bình Thạnh, Hồ Chí Minh", "Quận 7, TP.HCM")


def test_aliases_and_number_boundaries():
    assert text_matches("Phường 3, Quận 7, TP. HCM", "Quận 7, Thành phố Hồ Chí Minh")
    assert not text_matches("Quận 70, Hồ Chí Minh", "Quận 7, Hồ Chí Minh")
    assert not text_matches("Phường 17, Đà Nẵng", "Phường 7, Đà Nẵng")
    assert canonical("Q.07, TP.HCM") == "quan7 hochiminh"


def test_viewport_is_not_place_coordinates_and_narrower_area_is_retained():
    url = "https://www.google.com/maps/place/test/@10.739,106.708,13z/data=!3d10.777!4d106.700"
    assert place_coordinates(url) == (106.700, 10.777)
    assert place_coordinates("https://www.google.com/maps/@10.739,106.708,13z") is None
    assert not AreaMatcher("Phường Tân Mỹ, Quận 7, Hồ Chí Minh").matches(
        "Tân Hưng, Hồ Chí Minh",
        "https://www.google.com/maps/place/test/data=!3d10.7393684!4d106.70807",
    )


def test_polygon_holes_and_multipolygon():
    poly = {
        "type": "Polygon",
        "coordinates": [
            [[0, 0], [5, 0], [5, 5], [0, 5], [0, 0]],
            [[2, 2], [3, 2], [3, 3], [2, 3], [2, 2]],
        ],
    }
    assert in_geometry((1, 1), poly)
    assert not in_geometry((2.5, 2.5), poly)
    assert not in_geometry((6, 6), poly)
    assert in_geometry((1, 1), {"type": "MultiPolygon", "coordinates": [poly["coordinates"]]})


def test_retry_skipped_preserves_done_and_uses_same_job(auth, monkeypatch):
    monkeypatch.setattr("app.worker.crawl.apply_async", lambda *a, **k: None)
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area="Quận 7, TP.HCM",
            target=100,
            status="completed",
        )
        db.add(job)
        db.flush()
        db.add_all(
            [
                CrawlEntry(
                    job_id=job.id,
                    external_key="skipped",
                    url="https://www.google.com/maps/place/a",
                    name="A",
                    state="skipped",
                    error="Địa chỉ chưa khớp khu vực đã nhập; không tự gán khu vực.",
                    raw_data={"values": {"address": "Tân Hưng, Hồ Chí Minh"}},
                ),
                CrawlEntry(
                    job_id=job.id,
                    external_key="done",
                    url="https://www.google.com/maps/place/b",
                    name="B",
                    state="done",
                ),
            ]
        )
        db.commit()
        job_id = job.id
    response = auth.post(f"/api/v1/crawl-jobs/{job_id}/retry-area")
    assert response.status_code == 200, response.text
    assert response.json()["id"] == job_id and response.json()["status"] == "queued"
    assert response.json()["counts"] == {"done": 1, "pending": 1}
    assert auth.post(f"/api/v1/crawl-jobs/{job_id}/retry-area").status_code == 409
    with SessionLocal() as db:
        assert db.get(CrawlControl, 1).active_job_id == job_id
        entry = db.scalar(select(CrawlEntry).where(CrawlEntry.external_key == "skipped"))
        assert entry.raw_data["values"]["address"] == "Tân Hưng, Hồ Chí Minh"


def test_old_empty_completed_job_is_not_reported_as_success(auth):
    with SessionLocal() as db:
        job = CrawlJob(
            user_id=1,
            request_key=str(uuid.uuid4()),
            keyword="quán ăn",
            area="Quận 7, TP.HCM",
            target=100,
            status="completed",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    assert auth.get(f"/api/v1/crawl-jobs/{job_id}").json()["status"] == "no_results"
