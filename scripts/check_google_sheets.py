"""Check read-only access to the configured Google spreadsheet."""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def visible_error_body(raw):
    parser = VisibleText()
    try:
        parser.feed(raw)
    except Exception:
        return re.sub(r"\s+", " ", raw)[:1200]
    return re.sub(r"\s+", " ", " ".join(parser.parts))[:1200]


def get_json(url, access_token, label):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "LeadFinder-Google-Sheets-Check/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        content_type = exc.headers.get("Content-Type", "unknown")
        final_url = urllib.parse.urlsplit(exc.url)
        print(f"{label}: Google Sheets API trả HTTP {exc.code}.", file=sys.stderr)
        print(f"Content-Type: {content_type}", file=sys.stderr)
        print(f"Máy chủ phản hồi: {final_url.scheme}://{final_url.netloc}", file=sys.stderr)
        message = visible_error_body(raw)
        if message:
            print(f"Chi tiết: {message}", file=sys.stderr)
        else:
            print("Google không trả về nội dung lỗi đọc được.", file=sys.stderr)
    except Exception as exc:
        print(f"{label}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return None


def main():
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    access_token = os.getenv("GOOGLE_ACCESS_TOKEN", "").strip()
    missing = [
        key
        for key, value in (
            ("GOOGLE_SHEET_ID", spreadsheet_id),
            ("GOOGLE_ACCESS_TOKEN", access_token),
        )
        if not value
    ]
    if missing:
        print("Thiếu cấu hình: " + ", ".join(missing), file=sys.stderr)
        return 1

    encoded_id = urllib.parse.quote(spreadsheet_id, safe="")
    query = urllib.parse.urlencode(
        {"fields": "spreadsheetId,properties.title,sheets.properties.title"}
    )
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{encoded_id}?{query}"
    payload = get_json(url, access_token, "Đọc thông tin spreadsheet")
    if payload is None:
        return 1

    title = payload.get("properties", {}).get("title", "(không có tiêu đề)")
    tabs = [sheet.get("properties", {}).get("title", "") for sheet in payload.get("sheets", [])]
    print("Kết nối Google Sheets thành công.")
    print(f"Spreadsheet: {title}")
    print("Các tab hiện có: " + (", ".join(tabs) if tabs else "chưa có tab"))

    for tab in tabs:
        a1_range = urllib.parse.quote(f"'{tab}'!1:1", safe="")
        values_url = (
            f"https://sheets.googleapis.com/v4/spreadsheets/{encoded_id}"
            f"/values/{a1_range}"
        )
        row_result = get_json(values_url, access_token, f"Đọc hàng đầu tab {tab}")
        if row_result is None:
            return 1
        values = row_result.get("values", [])
        width = len(values[0]) if values else 0
        print(f"Đọc hàng đầu tab {tab} thành công ({width} ô có dữ liệu).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
