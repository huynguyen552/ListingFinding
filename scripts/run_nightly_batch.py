"""Run CSV-defined crawl jobs through the local Compose app and create one workbook."""

import argparse
import csv
import io
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from openpyxl import Workbook, load_workbook

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATUSES = {
    "blocked",
    "cancelled",
    "completed",
    "completed_with_errors",
    "failed",
    "no_results",
    "paused",
}
STOP_BATCH_STATUSES = {"blocked", "cancelled", "failed", "paused"}
MAX_QUERIES = 25
POLL_SECONDS = 5


@dataclass(frozen=True)
class Query:
    keyword: str
    area: str
    target: int
    enrich_website: bool


class LeadFinderAPI:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.csrf = ""
        cookies = urllib.request.HTTPCookieProcessor()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), cookies)

    def request(self, method, path, payload=None, csrf=False):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        request = urllib.request.Request(
            self.base_url + path, data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                body = response.read()
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            body = exc.read()
            try:
                details = json.loads(body.decode("utf-8")).get("message", "")
            except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
                details = body.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"API trả HTTP {exc.code}: {details}") from None
        if "json" in content_type:
            return json.loads(body.decode("utf-8"))
        return body

    def setup_session(self):
        status = self.request("GET", "/api/v1/setup")
        if not status.get("required"):
            raise RuntimeError(
                "Database của workflow không còn trống; không thể tạo phiên chạy tự động an toàn."
            )
        username = "gh_action_" + secrets.token_hex(6)
        password = secrets.token_urlsafe(24)
        session = self.request(
            "POST", "/api/v1/setup", {"username": username, "password": password}
        )
        self.csrf = session["csrf"]

    def start_job(self, query):
        return self.request(
            "POST",
            "/api/v1/crawl-jobs",
            {
                "keyword": query.keyword,
                "area": query.area,
                "target": query.target,
                "enrich_website": query.enrich_website,
                "request_key": secrets.token_hex(16),
            },
            csrf=True,
        )

    def get_job(self, job_id):
        return self.request("GET", f"/api/v1/crawl-jobs/{job_id}")

    def export_job(self, job_id):
        params = urllib.parse.urlencode(
            {"format": "xlsx", "crawl_job_id": job_id, "include_unverified_tax": "true"}
        )
        return self.request("GET", f"/api/v1/exports/download?{params}")

    def pause_job(self, job_id):
        return self.request("POST", f"/api/v1/crawl-jobs/{job_id}/pause", {}, csrf=True)


def parse_bool(value, default):
    value = value.strip().lower()
    if not value:
        return default
    if value in {"true", "1", "yes", "y", "co", "có"}:
        return True
    if value in {"false", "0", "no", "n", "khong", "không"}:
        return False
    raise ValueError("dùng true/false, yes/no hoặc 1/0")


def read_queries(path):
    text = path.read_text(encoding="utf-8-sig")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError(f"{path} chưa có dòng tiêu đề.")
    names = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = {"keyword", "area", "target"} - names.keys()
    if missing:
        raise ValueError("Thiếu cột bắt buộc: " + ", ".join(sorted(missing)))

    queries = []
    for row_number, row in enumerate(reader, start=2):
        if not any((value or "").strip() for value in row.values()):
            continue
        def value(name, default=""):
            column = names.get(name)
            return (row.get(column, default) or default).strip()

        try:
            enabled = parse_bool(value("enabled", "true"), True)
            if not enabled:
                continue
            keyword, area = value("keyword"), value("area")
            target = int(value("target"))
            enrich = parse_bool(value("enrich_website", "true"), True)
            if len(keyword) < 2 or len(keyword) > 150:
                raise ValueError("keyword cần dài từ 2 đến 150 ký tự")
            if len(area) < 2 or len(area) > 150:
                raise ValueError("area cần dài từ 2 đến 150 ký tự")
            if not 1 <= target <= 200:
                raise ValueError("target phải nằm trong khoảng 1–200")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Dòng {row_number}: {exc}") from None
        queries.append(Query(keyword, area, target, enrich))
        if len(queries) > MAX_QUERIES:
            raise ValueError(f"Chỉ nhận tối đa {MAX_QUERIES} dòng đang bật trong một đêm.")
    if not queries:
        raise ValueError("Không có dòng input nào đang bật.")
    return queries


def wait_for_api(api, timeout=240):
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            result = api.request("GET", "/api/v1/health/ready")
            if result.get("status") == "ready":
                return
            last_error = "API chưa sẵn sàng."
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"LeadFinder API chưa sẵn sàng sau {timeout} giây: {last_error}")


def wait_for_job(api, job_id, deadline):
    while time.monotonic() < deadline:
        job = api.get_job(job_id)
        if job["status"] in TERMINAL_STATUSES:
            return job, False
        time.sleep(POLL_SECONDS)
    try:
        api.pause_job(job_id)
    except Exception:
        pass
    pause_deadline = time.monotonic() + 45
    job = api.get_job(job_id)
    while job["status"] not in TERMINAL_STATUSES and time.monotonic() < pause_deadline:
        time.sleep(2)
        job = api.get_job(job_id)
    return job, True


def append_export(workbook, api, query, job_id):
    raw = api.export_job(job_id)
    source_book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    places_rows = source_book["Địa điểm"].iter_rows(values_only=True)
    place_headers = next(places_rows, None)
    if place_headers and workbook["Địa điểm"].max_row == 1:
        workbook["Địa điểm"].append(["Từ khóa", "Khu vực", *place_headers])
    for row in places_rows:
        workbook["Địa điểm"].append([query.keyword, query.area, *row])

    if "Nguồn theo trường" in source_book.sheetnames:
        rows = source_book["Nguồn theo trường"].iter_rows(values_only=True)
        headers = next(rows, None)
        if headers and workbook["Nguồn theo trường"].max_row == 1:
            workbook["Nguồn theo trường"].append(["Từ khóa", "Khu vực", *headers])
        for row in rows:
            workbook["Nguồn theo trường"].append([query.keyword, query.area, *row])
    source_book.close()


def append_job_detail(workbook, api, query, job_id):
    detail = api.get_job(job_id)
    for entry in detail.get("entries", []):
        if entry.get("error") or entry.get("state") != "done":
            workbook["Thông báo"].append(
                [
                    query.keyword,
                    query.area,
                    entry.get("name", ""),
                    entry.get("state", ""),
                    (entry.get("error") or "").replace("\n", " ")[:1000],
                ]
            )
    return detail


def save_workbook(workbook, path):
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.lstrip().startswith(("=", "+", "-", "@")):
                    cell.value = "'" + cell.value
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            values = [len(str(cell.value or "")) for cell in column]
            sheet.column_dimensions[column[0].column_letter].width = min(
                60, max(14, max(values, default=14) + 2)
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def run(args):
    queries = read_queries(args.input)
    api = LeadFinderAPI(os.getenv("LEADFINDER_BASE_URL", "http://127.0.0.1:5173"))
    workbook = Workbook()
    summary = workbook.active
    summary.title = "Tổng hợp"
    summary.append(
        [
            "Từ khóa",
            "Khu vực",
            "Mục tiêu",
            "Trạng thái",
            "Tìm thấy",
            "Đã lưu",
            "Bỏ qua",
            "Lỗi",
            "Cảnh báo website",
            "Thông báo",
        ]
    )
    workbook.create_sheet("Địa điểm")
    workbook.create_sheet("Nguồn theo trường")
    workbook.create_sheet("Thông báo").append(
        ["Từ khóa", "Khu vực", "Tên địa điểm", "Trạng thái", "Chi tiết"]
    )
    workbook.create_sheet("Lưu ý").append(
        [
            "Mã số thuế trong file có thể là ứng viên chưa xác minh; cần kiểm tra trạng thái trước khi sử dụng.",
        ]
    )
    workbook["Lưu ý"].append(
        [
            "Kết quả Google Maps có thể thay đổi theo thời điểm và giới hạn truy cập; danh sách không bảo đảm đầy đủ.",
        ]
    )
    workbook["Lưu ý"].append(
        [
            "Thông tin công khai không tự cấp quyền tái sử dụng; cần tuân thủ điều khoản của nguồn dữ liệu.",
        ]
    )
    had_failure = False
    try:
        wait_for_api(api)
        api.setup_session()
    except Exception as exc:
        message = str(exc)[:1000]
        workbook["Thông báo"].append(["", "", "", "startup_error", message])
        for query in queries:
            summary.append(
                [query.keyword, query.area, query.target, "Lỗi khởi động", 0, 0, 0, 1, 0, message]
            )
        save_workbook(workbook, args.output)
        print(f"Đã tạo workbook báo lỗi khởi động: {args.output}", flush=True)
        return 1

    batch_deadline = time.monotonic() + int(os.getenv("BATCH_TIMEOUT_SECONDS", "17000"))

    for index, query in enumerate(queries, start=1):
        print(f"Bắt đầu truy vấn {index}/{len(queries)}.", flush=True)
        job_id = ""
        try:
            job = api.start_job(query)
            job_id = job["id"]
            timed_out = False
            if job["status"] not in TERMINAL_STATUSES:
                job, timed_out = wait_for_job(api, job["id"], batch_deadline)
            append_job_detail(workbook, api, query, job["id"])
            try:
                append_export(workbook, api, query, job["id"])
            except Exception as exc:
                workbook["Thông báo"].append(
                    [query.keyword, query.area, "", "export_error", str(exc)[:1000]]
                )
                had_failure = True
            counts = job.get("counts", {})
            message = job.get("message", "")
            if timed_out:
                message = "Workflow đã hết thời gian chờ; giữ lại phần kết quả đã lưu. " + message
                had_failure = True
            outcome = {
                "keyword": query.keyword,
                "area": query.area,
                "target": query.target,
                "status": "Tạm dừng do hết thời gian" if timed_out else job["status"],
                "found": job.get("found", 0),
                "saved": counts.get("done", 0),
                "skipped": counts.get("skipped", 0),
                "failed": counts.get("failed", 0),
                "warnings": job.get("warnings", 0),
                "message": message,
            }
            summary.append(
                [
                    outcome["keyword"],
                    outcome["area"],
                    outcome["target"],
                    outcome["status"],
                    outcome["found"],
                    outcome["saved"],
                    outcome["skipped"],
                    outcome["failed"],
                    outcome["warnings"],
                    outcome["message"],
                ]
            )
            if job["status"] in STOP_BATCH_STATUSES or timed_out:
                had_failure = True
                for pending in queries[index:]:
                    summary.append(
                        [
                            pending.keyword,
                            pending.area,
                            pending.target,
                            "Chưa chạy",
                            0,
                            0,
                            0,
                            0,
                            0,
                            "Dừng batch sau lỗi/kết nối ở truy vấn trước.",
                        ]
                    )
                break
        except Exception as exc:
            had_failure = True
            message = str(exc)[:1000]
            partial = None
            if job_id:
                try:
                    api.pause_job(job_id)
                except Exception:
                    pass
                try:
                    partial = api.get_job(job_id)
                except Exception as recovery_error:
                    message += f" Không đọc lại được trạng thái job: {str(recovery_error)[:300]}"
                try:
                    append_job_detail(workbook, api, query, job_id)
                except Exception:
                    pass
                try:
                    append_export(workbook, api, query, job_id)
                except Exception as recovery_error:
                    workbook["Thông báo"].append(
                        [query.keyword, query.area, "", "partial_export_error", str(recovery_error)[:1000]]
                    )
            counts = (partial or {}).get("counts", {})
            found = (partial or {}).get("found", 0)
            saved = counts.get("done", 0)
            skipped = counts.get("skipped", 0)
            failed = counts.get("failed", 1)
            warnings = (partial or {}).get("warnings", 0)
            status = "Lỗi" if not partial else f"Lỗi theo dõi ({partial['status']})"
            if partial:
                message = f"Lỗi khi theo dõi; trạng thái đợt: {partial['status']}. {message}"
            summary.append(
                [
                    query.keyword,
                    query.area,
                    query.target,
                    status,
                    found,
                    saved,
                    skipped,
                    failed,
                    warnings,
                    message,
                ]
            )
            workbook["Thông báo"].append([query.keyword, query.area, "", "workflow_error", message])
            for pending in queries[index:]:
                summary.append(
                    [
                        pending.keyword,
                        pending.area,
                        pending.target,
                        "Chưa chạy",
                        0,
                        0,
                        0,
                        0,
                        0,
                        "Dừng batch sau lỗi ở truy vấn trước.",
                    ]
                )
            break

    save_workbook(workbook, args.output)
    print(f"Đã tạo workbook: {args.output}", flush=True)
    if had_failure:
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--validate-only", action="store_true", help="kiểm tra Secrets và CSV, không chạy crawler"
    )
    parser.add_argument(
        "--input", type=Path, default=ROOT / "automation" / "targets.csv", help="CSV đầu vào"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "action-results" / "leadfinder-nightly.xlsx",
        help="Đường dẫn workbook kết quả",
    )
    args = parser.parse_args()
    try:
        if args.validate_only:
            queries = read_queries(args.input)
            print(f"Input hợp lệ; có {len(queries)} truy vấn đang bật.")
            return 0
        return run(args)
    except Exception as exc:
        print(f"LeadFinder batch thất bại: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
