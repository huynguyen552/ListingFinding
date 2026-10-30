"""Load crawl targets from the Targets tab into the batch runner's CSV input."""

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://sheets.googleapis.com/v4"
TAB_NAME = "Targets"
OUTPUT = ROOT / "automation" / "targets.csv"
OUTPUT_HEADERS = ["keyword", "area", "target", "enrich_website", "enabled"]


def load_rows():
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    access_token = os.getenv("GOOGLE_ACCESS_TOKEN", "").strip()
    if not spreadsheet_id or not access_token:
        raise RuntimeError("Thiếu GOOGLE_SHEET_ID hoặc access token Google Sheets.")

    spreadsheet_id = urllib.parse.quote(spreadsheet_id, safe="")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {access_token}"}
    try:
        metadata_request = urllib.request.Request(
            f"{API_ROOT}/spreadsheets/{spreadsheet_id}?fields=sheets.properties.title",
            headers=headers,
        )
        with urllib.request.urlopen(metadata_request, timeout=45) as response:
            metadata = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"Không đọc được cấu trúc Google Sheet (HTTP {exc.code}). "
            f"Kiểm tra spreadsheet ID và quyền của service account. {details}"
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không kết nối được Google Sheets: {exc.reason}") from None

    sheet_titles = {
        item.get("properties", {}).get("title", "")
        for item in metadata.get("sheets", [])
    }
    if TAB_NAME not in sheet_titles:
        print(
            f"::warning::Chưa có tab '{TAB_NAME}'. Tạm dùng automation/targets.csv; "
            f"hãy tạo tab '{TAB_NAME}' để chỉnh input mà không cần commit.",
            flush=True,
        )
        return None

    a1_range = urllib.parse.quote(f"'{TAB_NAME}'!A:Z", safe="")
    query = urllib.parse.urlencode(
        {"majorDimension": "ROWS", "valueRenderOption": "FORMATTED_VALUE"}
    )
    request = urllib.request.Request(
        f"{API_ROOT}/spreadsheets/{spreadsheet_id}/values/{a1_range}?{query}",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"Không đọc được tab '{TAB_NAME}' (HTTP {exc.code}). "
            f"Kiểm tra quyền của service account. {details}"
        ) from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Không kết nối được Google Sheets: {exc.reason}") from None

    rows = payload.get("values", [])
    if not rows:
        raise RuntimeError(
            f"Tab '{TAB_NAME}' đang trống. Hãy thêm hàng tiêu đề: "
            + ", ".join(OUTPUT_HEADERS)
        )

    header_indexes = {}
    for index, value in enumerate(rows[0]):
        name = str(value).strip().lstrip("\ufeff").lower()
        if not name:
            continue
        if name in header_indexes:
            raise RuntimeError(f"Tab '{TAB_NAME}' có tiêu đề cột bị lặp: {name}")
        header_indexes[name] = index

    missing = {"keyword", "area", "target"} - header_indexes.keys()
    if missing:
        raise RuntimeError(
            f"Tab '{TAB_NAME}' thiếu cột bắt buộc: " + ", ".join(sorted(missing))
        )

    def cell(row, column, default=""):
        index = header_indexes.get(column)
        if index is None or index >= len(row) or row[index] is None:
            return default
        return str(row[index]).strip()

    output_rows = []
    for row in rows[1:]:
        values = [cell(row, column) for column in OUTPUT_HEADERS]
        if not any(values):
            continue
        if not values[3]:
            values[3] = "true"
        if not values[4]:
            values[4] = "true"
        output_rows.append(values)
    return output_rows


def main():
    try:
        rows = load_rows()
        if rows is None:
            return 0
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        with OUTPUT.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(OUTPUT_HEADERS)
            writer.writerows(rows)
        print(
            f"Đã nạp {len(rows)} dòng từ Google Sheet tab '{TAB_NAME}' vào input tạm.",
            flush=True,
        )
        return 0
    except Exception as exc:
        print(f"Không nạp được input từ Google Sheets: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
