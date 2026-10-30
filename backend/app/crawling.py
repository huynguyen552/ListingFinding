"""Google Maps discovery and website enrichment with persistent checkpoints."""

import hashlib
import os
import re
import secrets
import time
from urllib.parse import quote, unquote, urlsplit

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright
from sqlalchemy import func, select

from .area_matching import AreaMatcher, text_matches
from .crawl_network import FetchError, fetch, require_robots
from .crawl_stats import crawl_counts
from .db import SessionLocal
from .extraction import extract_website
from .importing import FIELDS, identity, website
from .models import (
    CrawlControl,
    CrawlEntry,
    CrawlJob,
    ExternalPlace,
    Location,
    Observation,
    Source,
    now,
)

TERMINAL = {"completed", "completed_with_errors", "failed", "cancelled", "blocked"}

DETAIL_SCRIPT = """() => {
  const text = sel => document.querySelector(sel)?.getAttribute('aria-label')?.replace(/^[^:]+:\\s*/, '').trim() || '';
  const headings = [...document.querySelectorAll('h1')].filter(e =>
    e.textContent.trim() && !/^(?:(?:Kết quả|Results)$|Được tài trợ|Sponsored)/i.test(e.textContent.trim()));
  return {
    name: headings[0]?.textContent.trim() || '',
    address: text('[data-item-id="address"]'),
    phone: text('[data-item-id^="phone:tel:"]'),
    website: document.querySelector('a[data-item-id="authority"]')?.href || '',
    category: document.querySelector('button[jsaction$=".category"]')?.textContent.trim() || ''
  };
}"""


class StopCrawl(Exception):
    pass


class BlockedCrawl(Exception):
    pass


class MapBrowser:
    """Start Chromium only for a Maps read; release it before storing/enriching."""

    def __init__(self):
        self.playwright = None
        self.browser = None

    def __enter__(self):
        return self

    def page(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(
            headless=True, args=["--disable-dev-shm-usage", "--disable-features=BackForwardCache"]
        )
        context = self.browser.new_context(
            locale="vi-VN", viewport={"width": 1365, "height": 900}, service_workers="block"
        )
        context.route("**/*", browser_route)
        page = context.new_page()
        page.set_default_timeout(5000)
        return page

    def read(self, url):
        try:
            return read_place(self.page(), url)
        except BrowserError:
            if self.browser and self.browser.is_connected():
                raise ValueError(
                    "Không đọc được địa điểm từ Google Maps; có thể bấm Tiếp tục để thử lại."
                ) from None
            raise
        finally:
            self.close()

    def close(self):
        try:
            if self.browser:
                try:
                    self.browser.close()
                except BrowserError:
                    pass
        finally:
            self.browser = None
            if self.playwright:
                try:
                    self.playwright.stop()
                finally:
                    self.playwright = None

    def __exit__(self, *exc):
        self.close()


def validated_place(data):
    data = dict(data)
    if not data.get("name") or not data.get("address"):
        raise ValueError("Chưa đọc được tên hoặc địa chỉ của địa điểm.")
    try:
        data["website"] = website(data.get("website", ""))
    except ValueError:
        data["website"] = ""
    return data


def place_key(url):
    match = re.search(r"!1s([^!/?]+)", unquote(url))
    value = match.group(1) if match else url.split("?")[0]
    return hashlib.sha256(value.encode()).hexdigest()


def source_url(url):
    match = re.search(r"!1s0x[0-9a-f]+:0x([0-9a-f]+)", unquote(url), re.I)
    return "https://www.google.com/maps?cid=" + str(int(match.group(1), 16)) if match else url[:300]


def in_area(address, area):
    return text_matches(address, area)


def tick(job_id, token, message=None):
    if os.getenv("QUEUE_MODE") == "database":
        from .queueing import shutdown_requested

        if shutdown_requested.is_set():
            raise StopCrawl()
    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        if not job or job.run_token != token or job.status != "running":
            raise StopCrawl()
        job.heartbeat = now()
        job.updated_at = now()
        if message:
            job.message = message
        db.commit()


def finish(job_id, token, status, message):
    with SessionLocal() as db:
        control = db.scalar(select(CrawlControl).where(CrawlControl.id == 1).with_for_update())
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if not job or job.run_token != token:
            return
        if job.status == "cancelling":
            status, message = "cancelled", "Đã hủy. Kết quả đã thu thập được giữ lại."
        elif job.status == "pausing":
            status, message = "paused", "Đã tạm dừng. Có thể tiếp tục phần chưa xong."
        job.status, job.message, job.updated_at = status, message, now()
        if control and control.active_job_id == job_id:
            control.active_job_id = None
        db.commit()


def check_block(page):
    if "/sorry/" in page.url or "consent.google" in page.url:
        raise BlockedCrawl(
            "Google yêu cầu xác minh hoặc chấp thuận. Đã dừng, không tự vượt xác minh."
        )
    if page.locator('form[action*="sorry"], iframe[src*="recaptcha/api2/bframe"]').count():
        raise BlockedCrawl("Google yêu cầu CAPTCHA. Hãy thử lại vào lúc khác.")


def browser_route(route):
    request = route.request
    host = (urlsplit(request.url).hostname or "").lower()
    allowed = ("google.com", "gstatic.com", "googleapis.com", "googleusercontent.com", "ggpht.com")
    if request.resource_type in ("image", "media", "font") or not any(
        host == h or host.endswith("." + h) for h in allowed
    ):
        route.abort()
    else:
        route.continue_()


def discover(page, job_id, token, keyword, area, target):
    tick(job_id, token, "Đang tìm địa điểm trên Google Maps…")
    query = keyword + " tại " + area + " Việt Nam"
    page.goto(
        "https://www.google.com/maps/search/" + quote(query) + "/?hl=vi",
        wait_until="domcontentloaded",
        timeout=45000,
    )
    check_block(page)
    try:
        page.locator('[role="feed"], [data-item-id="address"]').first.wait_for(timeout=25000)
    except BrowserTimeout:
        check_block(page)
        body = page.locator("body").inner_text(timeout=5000)
        if re.search(r"không tìm thấy|couldn't find|no results", body, re.I):
            return
        raise BlockedCrawl(
            "Chưa đọc được kết quả Google Maps. Có thể trang bị giới hạn hoặc thay đổi giao diện."
        ) from None
    # Maps temporarily hides the feed from the accessibility tree while updating.
    # Keep using its DOM node and allow slower instances time to finish rendering.
    feed = page.locator('[role="feed"]')
    seen = set()
    idle = 0
    for _ in range(60):
        tick(job_id, token)
        check_block(page)
        links = page.locator('a[href*="/maps/place/"]').evaluate_all(
            "els => els.map(e => ({url:e.href,name:e.getAttribute('aria-label')||e.textContent||''}))"
        )
        if not feed.count() and page.locator('[data-item-id="address"]').count():
            direct = validated_place(page.evaluate(DETAIL_SCRIPT))
            direct_name, direct_address = direct["name"], direct["address"]
            links = [
                {
                    "url": page.url,
                    "name": direct_name,
                    "details": direct,
                    "direct_key": identity(
                        {
                            "name": direct_name,
                            "address": direct_address,
                            "city": AreaMatcher(area).city_for(direct_address),
                            "website": "",
                        }
                    ),
                }
            ]
        previous_seen = len(seen)
        with SessionLocal() as db:
            job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
            if not job or job.run_token != token or job.status != "running":
                raise StopCrawl()
            for link in links:
                if len(seen) >= min(target * 3, 200):
                    break
                parts = urlsplit(link["url"])
                if parts.hostname != "www.google.com" or not (
                    parts.path.startswith("/maps/place/")
                    or (link.get("direct_key") and parts.path.startswith("/maps/search/"))
                ):
                    continue
                key = link.get("direct_key") or place_key(link["url"])
                if key in seen:
                    continue
                seen.add(key)
                existing = db.scalar(
                    select(CrawlEntry).where(
                        CrawlEntry.job_id == job_id, CrawlEntry.external_key == key
                    )
                )
                if not existing:
                    db.add(
                        CrawlEntry(
                            job_id=job_id,
                            external_key=key,
                            url=link["url"],
                            name=link["name"][:300],
                            raw_data=(
                                {"values": link["details"], "collected_at": now()}
                                if link.get("details")
                                else None
                            ),
                        )
                    )
                elif existing.state == "pending" and not existing.raw_data and link.get("details"):
                    existing.raw_data = {"values": link["details"], "collected_at": now()}
            db.commit()
        idle = 0 if len(seen) > previous_seen else idle + 1
        tick(job_id, token, f"Đã tìm thấy {len(seen)} địa điểm ứng viên…")
        if len(seen) >= min(target * 3, 200) or idle >= 4 or not feed.count():
            break
        try:
            feed.evaluate("el => {el.scrollTop = el.scrollHeight;}", timeout=30000)
        except BrowserTimeout:
            check_block(page)
            tick(job_id, token, "Danh sách Maps phản hồi chậm; đang đọc các địa điểm đã tìm thấy…")
            # Preserve the unfinished discovery checkpoint. Process saved candidates
            # first instead of discarding them or claiming the search was exhausted.
            return False
        time.sleep(2)
    with SessionLocal() as db:
        job = db.get(CrawlJob, job_id)
        if job.run_token == token:
            job.discovery_complete = True
            db.commit()


def read_place(page, url):
    parts = urlsplit(url)
    if parts.hostname != "www.google.com" or not parts.path.startswith(
        ("/maps/place/", "/maps/search/")
    ):
        raise ValueError("Link địa điểm không hợp lệ.")
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    check_block(page)
    try:
        page.locator('[data-item-id="address"]').wait_for(timeout=20000)
    except BrowserTimeout:
        check_block(page)
        raise ValueError("Địa điểm chưa có địa chỉ đọc được.") from None
    return validated_place(page.evaluate(DETAIL_SCRIPT))


def save_place(job_id, token, entry_id, values, extra_observations=(), website_error=""):
    limits = {
        "name": 300,
        "address": 500,
        "city": 150,
        "category": 100,
        "phone": 150,
        "website": 500,
        "tax_code": 50,
    }
    values = {field: str(values.get(field, "")).strip()[:limit] for field, limit in limits.items()}
    with SessionLocal() as db:
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if not job or job.run_token != token or job.status != "running":
            raise StopCrawl()
        entry = db.get(CrawlEntry, entry_id)
        google = db.get(Source, "google_maps")
        if not google or not google.allow_store:
            raise ValueError("Nguồn Google Maps hiện không cho phép lưu.")
        ref = source_url(entry.url)
        linked = db.get(ExternalPlace, entry.external_key)
        row = (
            db.get(Location, linked.location_id)
            if linked
            else db.scalar(select(Location).where(Location.identity_key == identity(values)))
        )
        if not row:
            row = Location(
                identity_key=identity(values),
                **{f: values.get(f, "") for f in FIELDS},
                provenance={f: "google_maps" for f in FIELDS if values.get(f)},
            )
            db.add(row)
            db.flush()
        if not linked:
            db.add(ExternalPlace(external_key=entry.external_key, location_id=row.id))
        provenance = dict(row.provenance)
        for field in FIELDS:
            value = values.get(field, "")
            if not value:
                continue
            # Add to blank fields only. User-confirmed values are never overwritten.
            if not getattr(row, field) and provenance.get(field) != "manual":
                setattr(row, field, value)
                provenance[field] = "google_maps"
            existing = db.scalar(
                select(Observation.id).where(
                    Observation.location_id == row.id,
                    Observation.field == field,
                    Observation.value == value,
                    Observation.source_id == "google_maps",
                    Observation.source_ref == ref,
                )
            )
            if not existing:
                db.add(
                    Observation(
                        location_id=row.id,
                        field=field,
                        value=value,
                        source_id="google_maps",
                        source_ref=ref,
                    )
                )
        website_source = db.get(Source, "website")
        if website_source and website_source.allow_store:
            for field, value, url in extra_observations:
                value = str(value)[: limits.get(field, 500)]
                if (
                    field in FIELDS
                    and not getattr(row, field)
                    and provenance.get(field) != "manual"
                ):
                    setattr(row, field, value)
                    provenance[field] = "website"
                exists = db.scalar(
                    select(Observation.id).where(
                        Observation.location_id == row.id,
                        Observation.field == field,
                        Observation.value == value,
                        Observation.source_id == "website",
                        Observation.source_ref == url[:300],
                    )
                )
                if not exists:
                    db.add(
                        Observation(
                            location_id=row.id,
                            field=field,
                            value=value,
                            source_id="website",
                            source_ref=url[:300],
                        )
                    )
        row.provenance = provenance
        row.version += 1
        row.updated_at = now()
        entry.state, entry.location_id, entry.error = "done", row.id, website_error[:500]
        job.heartbeat = now()
        db.commit()


def record_entry_error(job_id, token, entry_id, state, message):
    with SessionLocal() as db:
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if not job or job.run_token != token or job.status != "running":
            raise StopCrawl()
        entry = db.get(CrawlEntry, entry_id)
        entry.state, entry.error = state, message[:1000]
        job.heartbeat = now()
        db.commit()


def run_crawl(job_id):
    token = secrets.token_hex(24)
    with SessionLocal() as db:
        job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
        if not job or job.status != "queued":
            return
        job.status, job.run_token, job.heartbeat = "running", token, now()
        keyword, area, target, enrich = job.keyword, job.area, job.target, job.enrich_website
        discovery_complete = job.discovery_complete
        source = db.get(Source, "google_maps")
        web_source = db.get(Source, "website")
        if not source or not source.allow_store:
            job.status, job.message = "failed", "Nguồn Google Maps đã bị tắt."
            control = db.get(CrawlControl, 1)
            if control and control.active_job_id == job_id:
                control.active_job_id = None
            db.commit()
            return
        enrich = enrich and bool(web_source and web_source.allow_store)
        db.commit()
    robots_cache = {}
    area_matcher = AreaMatcher(area)
    discovery_incomplete = False
    try:
        with MapBrowser() as maps:
            if not discovery_complete:
                try:
                    discovery_incomplete = (
                        discover(maps.page(), job_id, token, keyword, area, target) is False
                    )
                finally:
                    maps.close()
            while True:
                tick(job_id, token)
                with SessionLocal() as db:
                    done = crawl_counts(db, job_id)[0].get("done", 0)
                    entry = db.scalar(
                        select(CrawlEntry)
                        .where(CrawlEntry.job_id == job_id, CrawlEntry.state == "pending")
                        .order_by(CrawlEntry.id)
                    )
                    if done >= target or not entry:
                        break
                    entry_id, url = entry.id, entry.url
                    cached = entry.raw_data
                try:
                    tick(job_id, token, f"Đang đọc địa điểm; đã lưu {done}/{target}…")
                    values = (
                        dict(cached["values"])
                        if cached and cached.get("values")
                        else maps.read(url)
                    )
                    with SessionLocal() as db:
                        locked_job = db.scalar(
                            select(CrawlJob).where(CrawlJob.id == job_id).with_for_update()
                        )
                        if locked_job.run_token != token or locked_job.status != "running":
                            raise StopCrawl()
                        record = db.get(CrawlEntry, entry_id)
                        record.raw_data = {
                            "values": values,
                            "collected_at": (cached or {}).get("collected_at", now()),
                        }
                        record.name = values.get("name", record.name)[:300]
                        db.commit()
                    area_ok, area_reason = area_matcher.evaluate(values["address"], url)
                    if not area_ok:
                        record_entry_error(
                            job_id,
                            token,
                            entry_id,
                            "skipped",
                            "Địa chỉ chưa khớp khu vực đã nhập: "
                            + area_reason
                            + " Địa chỉ: "
                            + values["address"],
                        )
                        continue
                    values["city"] = area_matcher.city_for(values["address"])
                    extra, warning = [], ""
                    if enrich and values.get("website"):
                        urls = [values["website"]]
                        visited = set()
                        for _ in range(3):
                            if not urls:
                                break
                            tick(job_id, token, f"Đang đọc website của {values['name']}…")
                            site_url = urls.pop(0)
                            if site_url in visited:
                                continue
                            visited.add(site_url)
                            try:
                                require_robots(site_url, robots_cache)
                                time.sleep(2)
                                status, html, final_url = fetch(
                                    site_url,
                                    before_request=lambda u: require_robots(u, robots_cache),
                                )
                                if status != 200:
                                    warning = (
                                        f"Website trả HTTP {status}; đã giữ dữ liệu Google Maps."
                                    )
                                    continue
                                extracted, contact_links = extract_website(html, final_url)
                                extra.extend(
                                    (f, value, final_url) for f, value in extracted.items() if value
                                )
                                urls.extend(
                                    link
                                    for link in contact_links
                                    if link not in visited and link not in urls
                                )
                            except FetchError as exc:
                                warning = str(exc)[:300]
                    save_place(job_id, token, entry_id, values, extra, warning)
                except (BrowserError, ValueError) as exc:
                    if isinstance(exc, BrowserError):
                        raise
                    message = (
                        "Không đọc được địa điểm từ Google Maps; có thể bấm Tiếp tục để thử lại."
                        if isinstance(exc, BrowserError)
                        else str(exc)[:300]
                    )
                    record_entry_error(job_id, token, entry_id, "failed", message)
                time.sleep(2)
        with SessionLocal() as db:
            count = crawl_counts(db, job_id)[0].get("done", 0)
            errors = db.scalar(
                select(func.count())
                .select_from(CrawlEntry)
                .where(CrawlEntry.job_id == job_id, CrawlEntry.state == "failed")
            )
        if discovery_incomplete and count < target:
            finish(
                job_id,
                token,
                "paused",
                f"Đã lưu {count}/{target} địa điểm. Danh sách Maps phản hồi chậm; "
                "đã giữ kết quả. Bấm Tiếp tục để tìm và đọc phần còn lại.",
            )
            return
        finish(
            job_id,
            token,
            "completed_with_errors" if errors else ("no_results" if count == 0 else "completed"),
            f"Đã lưu {count} địa điểm. "
            + (
                "Đã đạt số lượng mục tiêu."
                if count >= target
                else "Đã hết kết quả đọc được phù hợp; không bảo đảm tìm đủ mục tiêu."
            ),
        )
    except StopCrawl:
        finish(job_id, token, "paused", "Đã dừng tác vụ.")
    except BlockedCrawl as exc:
        finish(job_id, token, "blocked", str(exc))
    except Exception:
        # Keep raw browser errors/URLs out of the UI and avoid exposing credentials.
        import logging

        logging.getLogger("leadfinder").exception("crawl_failed job=%s", job_id)
        finish(
            job_id,
            token,
            "failed",
            "Không mở được trình duyệt hoặc đọc được nguồn. Bấm Tiếp tục để thử lại; chi tiết lỗi được lưu trong nhật ký hệ thống.",
        )
