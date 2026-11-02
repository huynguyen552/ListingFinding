"""Look up existing candidate tax codes with VietQR and add a review sheet."""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://api.vietqr.io/v2/business/"
REQUEST_INTERVAL_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 15
MAX_RETRIES_ON_RATE_LIMIT = 1
HEADERS = [
    "Từ khóa",
    "Khu vực",
    "Mã địa điểm",
    "Tên quán",
    "Địa chỉ quán",
    "MST ứng viên",
    "Kết quả tra cứu VietQR",
    "MST trả về",
    "Tên pháp nhân/hộ kinh doanh",
    "Địa chỉ đăng ký MST",
    "Mô tả phản hồi",
    "Dữ liệu cập nhật lúc",
    "Thời điểm tra cứu",
]


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def local_now():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")


def retry_after_seconds(headers):
    value = headers.get("Retry-After", "").strip()
    if value:
        try:
            return max(1, int(float(value)))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                return max(1, int((retry_at - datetime.now(timezone.utc)).total_seconds()))
            except (TypeError, ValueError, OverflowError):
                pass
    reset = headers.get("X-RateLimit-Reset", "").strip()
    try:
        return max(1, int(float(reset) - time.time()))
    except ValueError:
        return 5


def request_once(tax_code):
    url = API_ROOT + urllib.parse.quote(tax_code, safe="")
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "LeadFinder/0.2 (+https://github.com/huynguyen552/ListingFinding)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read(256_000).decode("utf-8", errors="replace")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                payload = {"desc": "API trả JSON không đúng cấu trúc."}
            return response.status, response.headers, payload
    except urllib.error.HTTPError as exc:
        body = exc.read(256_000).decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {"desc": body[:500]}
        if not isinstance(payload, dict):
            payload = {"desc": "API trả JSON không đúng cấu trúc."}
        return exc.code, exc.headers, payload
    except (OSError, TimeoutError, urllib.error.URLError) as exc:
        return 0, {}, {"desc": f"Lỗi kết nối: {type(exc).__name__}"}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 200, {}, {"desc": "Phản hồi không phải JSON hợp lệ."}


def lookup(tax_code):
    for attempt in range(MAX_RETRIES_ON_RATE_LIMIT + 1):
        http_status, headers, payload = request_once(tax_code)
        if http_status != 429:
            break
        if attempt == MAX_RETRIES_ON_RATE_LIMIT:
            return {
                "result": "VietQR giới hạn lượt gọi (429)",
                "description": str(payload.get("desc", ""))[:500],
                "stop": True,
            }
        delay = retry_after_seconds(headers)
        if delay > 60:
            return {
                "result": "VietQR yêu cầu chờ lâu; dừng lượt tra cứu (429)",
                "description": str(payload.get("desc", ""))[:500],
                "stop": True,
            }
        print(f"VietQR trả 429; chờ {delay} giây theo Retry-After rồi thử lại một lần.", flush=True)
        time.sleep(delay)

    if http_status == 0:
        return {
            "result": "Lỗi kết nối VietQR",
            "description": str(payload.get("desc", ""))[:500],
            "stop": True,
            "stop_reason": "Lỗi kết nối; dừng tra cứu các MST còn lại",
        }
    if http_status >= 400:
        return {
            "result": f"VietQR trả HTTP {http_status}",
            "description": str(payload.get("desc", ""))[:500],
            "stop": http_status >= 500,
            "stop_reason": "VietQR lỗi máy chủ; dừng tra cứu các MST còn lại",
        }

    code = str(payload.get("code", ""))
    description = str(payload.get("desc", ""))[:500]
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    returned_id = str(data.get("id", ""))
    if code == "00":
        if not returned_id:
            result = "API thành công nhưng thiếu MST trả về"
        elif digits(returned_id) == digits(tax_code):
            result = "Tra cứu thấy MST"
        else:
            result = "MST trả về không khớp"
    elif code == "51":
        result = "VietQR báo MST không hợp lệ"
    elif code == "52":
        result = "VietQR không tìm thấy MST"
    else:
        result = f"VietQR trả mã {code or 'không rõ'}"

    return {
        "result": result,
        "returned_id": returned_id,
        "legal_name": str(data.get("name", "")),
        "registered_address": str(data.get("address", "")),
        "description": description,
        "updated_at": str(data.get("updatedAt", "")),
        "stop": False,
    }


def value(row, indexes, name):
    index = indexes.get(name)
    return row[index] if index is not None and index < len(row) else ""


def sheet_text(value, limit=2000):
    text = str(value or "")[:limit]
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def verify_workbook(path, max_lookups):
    workbook = load_workbook(path)
    if "Địa điểm" not in workbook.sheetnames:
        raise ValueError("Workbook không có sheet Địa điểm.")

    place_sheet = workbook["Địa điểm"]
    rows = place_sheet.iter_rows(values_only=True)
    header_row = next(rows, None)
    if not header_row:
        raise ValueError("Sheet Địa điểm chưa có tiêu đề.")
    indexes = {str(name or "").strip(): index for index, name in enumerate(header_row)}
    tax_header = next((name for name in indexes if name.startswith("MST")), None)
    if tax_header is None:
        raise ValueError("Không tìm thấy cột MST trong sheet Địa điểm.")

    source_rows = []
    for row in rows:
        candidate = str(value(row, indexes, tax_header) or "").strip()
        if candidate:
            source_rows.append((row, candidate, digits(candidate)))

    lookup_codes = list(dict.fromkeys(code for _, _, code in source_rows if len(code) in (10, 13)))
    max_lookups = max(0, max_lookups)
    results = {}
    stop_lookups = False
    stop_reason = "VietQR đang giới hạn lượt gọi; chưa tra cứu"
    attempted = 0
    for code in lookup_codes[:max_lookups]:
        if attempted:
            time.sleep(REQUEST_INTERVAL_SECONDS)
        result = lookup(code)
        results[code] = result
        attempted += 1
        if result.get("stop"):
            stop_lookups = True
            stop_reason = result.get("stop_reason", stop_reason)
            break

    review = (
        workbook["Xác minh MST"]
        if "Xác minh MST" in workbook.sheetnames
        else workbook.create_sheet("Xác minh MST")
    )
    if review.max_row:
        review.delete_rows(1, review.max_row)
    review.append(HEADERS)
    record_count = 0
    for row, candidate, code in source_rows:
        if len(code) not in (10, 13):
            result = {"result": "MST sai định dạng; không gửi tra cứu"}
        elif code in results:
            result = results[code]
        elif stop_lookups:
            result = {"result": stop_reason}
        else:
            result = {"result": f"Chưa tra cứu; vượt giới hạn {max_lookups} MST/lượt"}

        review.append(
            [
                sheet_text(value(row, indexes, "Từ khóa")),
                sheet_text(value(row, indexes, "Khu vực")),
                sheet_text(value(row, indexes, "Mã địa điểm")),
                sheet_text(value(row, indexes, "Tên quán")),
                sheet_text(value(row, indexes, "Địa chỉ")),
                sheet_text(candidate, 50),
                sheet_text(result.get("result", "Chưa tra cứu")),
                sheet_text(result.get("returned_id", ""), 50),
                sheet_text(result.get("legal_name", "")),
                sheet_text(result.get("registered_address", "")),
                sheet_text(result.get("description", "")),
                sheet_text(result.get("updated_at", ""), 100),
                local_now(),
            ]
        )
        record_count += 1

    notes = workbook["Lưu ý"] if "Lưu ý" in workbook.sheetnames else workbook.create_sheet("Lưu ý")
    note = (
        "VietQR chỉ tra cứu thông tin theo MST ứng viên; kết quả tìm thấy không chứng minh quán thuộc "
        "pháp nhân/hộ kinh doanh trả về. Đối chiếu tên và địa chỉ đăng ký trước khi xác nhận. "
        "VietQR thông báo API này ngừng hoạt động từ 01/03/2027."
    )
    if not any(
        str(cell.value or "").startswith("VietQR chỉ tra cứu")
        for row in notes.iter_rows()
        for cell in row
    ):
        notes.append([note])

    workbook.save(path)
    print(
        f"VietQR: đã tra {attempted}/{len(lookup_codes)} MST duy nhất; "
        f"ghi {record_count} dòng vào sheet Xác minh MST.",
        flush=True,
    )
    workbook.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workbook",
        type=Path,
        default=Path(
            os.getenv("LEADFINDER_WORKBOOK", ROOT / "action-results" / "leadfinder-nightly.xlsx")
        ),
    )
    parser.add_argument(
        "--max-lookups", type=int, default=int(os.getenv("VIETQR_MAX_LOOKUPS", "100"))
    )
    args = parser.parse_args()
    try:
        verify_workbook(args.workbook, args.max_lookups)
        return 0
    except Exception as exc:
        print(f"Bổ sung tra cứu VietQR thất bại: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
