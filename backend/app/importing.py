import csv
import hashlib
import io
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

FIELDS = ["name", "address", "city", "category", "phone", "website", "tax_code"]
ALIASES = {
    "ten quan": "name",
    "ten": "name",
    "dia chi": "address",
    "tinh/thanh": "city",
    "tinh thanh": "city",
    "thanh pho": "city",
    "loai quan": "category",
    "sdt": "phone",
    "so dien thoai": "phone",
    "mst": "tax_code",
}


def normalized(value):
    text = (
        unicodedata.normalize("NFD", value.replace("đ", "d").replace("Đ", "D"))
        .encode("ascii", "ignore")
        .decode()
        .lower()
    )
    return re.sub(r"\s+", " ", text).strip()


def website(value):
    if not value:
        return ""
    value = value if "://" in value else "https://" + value
    parts = urlsplit(value)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise ValueError("Website phải là địa chỉ HTTP/HTTPS hợp lệ.")
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def identity(row):
    # Never use shared phone/tax code as a branch identifier.
    def exact(value):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value).casefold()).strip()

    key = (
        ("address", exact(row["name"]), exact(row["address"]), exact(row.get("city", "")))
        if row["name"] and row["address"]
        else ("website", row["website"])
    )
    return hashlib.sha256(repr(key).encode()).hexdigest()


def parse_csv(data):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("File cần dùng mã hóa UTF-8. Hãy lưu lại CSV UTF-8 từ Excel.")
    try:
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("File chưa có hàng tiêu đề.")
    mapping = {}
    for header in reader.fieldnames:
        field = ALIASES.get(normalized(header), normalized(header))
        if field in FIELDS:
            if field in mapping.values():
                raise ValueError(f"Hai cột cùng ánh xạ đến {field}. Hãy sửa tiêu đề.")
            mapping[header] = field
    if not mapping:
        raise ValueError("Không nhận ra cột dữ liệu. Hãy dùng file CSV mẫu.")
    rows = []
    try:
        for index, raw in enumerate(reader, 2):
            if len(rows) >= 1000:
                raise ValueError("Mỗi lần nhập tối đa 1.000 dòng.")
            if not any(str(v or "").strip() for v in raw.values()):
                continue
            row = {field: "" for field in FIELDS}
            errors = []
            for header, field in mapping.items():
                row[field] = (raw.get(header) or "").strip()
            limits = {
                "name": 300,
                "address": 500,
                "city": 150,
                "category": 100,
                "phone": 150,
                "website": 500,
                "tax_code": 50,
            }
            if any(len(v) > limits[k] for k, v in row.items()):
                errors.append("Một ô vượt quá giới hạn ký tự của trường.")
            if None in raw:
                errors.append("Số cột trong dòng không khớp tiêu đề.")
            try:
                row["website"] = website(row["website"])
            except ValueError as exc:
                errors.append(str(exc))
            if not (row["name"] and row["address"]) and not row["website"]:
                errors.append("Cần tên + địa chỉ hoặc website.")
            rows.append({"line": index, "data": row, "errors": errors})
    except csv.Error:
        raise ValueError("Cấu trúc CSV không hợp lệ.")
    if not rows:
        raise ValueError("File chưa có dữ liệu.")
    return rows, mapping


def safe_cell(value):
    text = str(value or "")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text
