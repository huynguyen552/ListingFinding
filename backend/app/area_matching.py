"""Address aliases and local boundary checks; no geocoding requests at runtime."""

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

from .importing import normalized


def canonical(value):
    text = re.sub(r"[^a-z0-9]+", " ", normalized(value)).strip()
    # Preserve the named district level: today's ward Tân Phú has the same
    # name as the former district but a different, smaller boundary.
    text = re.sub(r"\b(?:quan|q|district|dist)\s+tan phu\b", "quantanphu", text)
    text = re.sub(r"\btan phu\s+district\b", "quantanphu", text)
    text = re.sub(
        r"\b(?:quan|q|district|dist|d)\s*0*(\d+)\b", lambda m: "quan" + str(int(m[1])), text
    )
    text = re.sub(r"\b(?:phuong|p|ward|w)\s*0*(\d+)\b", lambda m: "phuong" + str(int(m[1])), text)
    text = re.sub(r"\b(?:q|district|dist)\s+(?=[a-z])", "quan ", text)
    text = re.sub(
        r"\b(?:ho chi minh(?: city)?|hochiminh|tp\s*hcm|tphcm|hcmc|hcm|sai gon|saigon)\b",
        "hochiminh",
        text,
    )
    text = re.sub(
        r"\b(?:thanh pho|city of|city|province|tinh|tp|phuong|ward|xa|commune|huyen|p)\s+",
        "",
        text,
    )
    text = re.sub(r"\bviet nam\b", "vietnam", text)
    return re.sub(r"\s+", " ", text).strip()


def contains(text, part):
    return bool(part) and bool(re.search(r"(?<!\w)" + re.escape(part) + r"(?!\w)", text))


def split_parts(value):
    # Labelled components can be understood even when the user omits commas.
    value = re.sub(
        r"\s+(?=(?:phường|phuong|p\.|quận|quan|q\.|huyện|huyen|thành phố|thanh pho|tp\.|tỉnh|tinh|xã|xa|ward|district)\s*[^\s,;])",
        ",",
        value,
        flags=re.I,
    )
    return [part.strip() for part in re.split(r"[,;\n]+", value) if part.strip()]


def parts_of(area):
    return [canonical(part) for part in split_parts(area) if canonical(part)]


def admin_components(address):
    return {re.sub(r"\s+\d{5,6}$", "", part) for part in parts_of(address)}


STREET_PREFIX = re.compile(r"^(?:(?:đường|duong|street|road)\s+|(?:đ|d|st|rd)\.\s*)", re.I)
HOUSE = re.compile(
    r"^(?:(?:so|số)\s+)?\d+[a-z]?(?:\s*[/\-]\s*\d+[a-z]?)*(?:\s+[a-z](?=\s))?\s+", re.I
)
HOUSE_ONLY = re.compile(r"^(?:so\s+)?\d+[a-z]?(?:\s*[/\-]\s*\d+[a-z]?)*$", re.I)


def street_name(value):
    # Strip the label before removing accents: Dương is a family name,
    # while Đường is the road designator.
    text = normalized(STREET_PREFIX.sub("", value.strip()))
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    text = re.sub(r"^(?:so\s+)?0*(\d+)\b", lambda m: "streetnumber" + str(int(m[1])), text)
    return re.sub(r"\s+", " ", text)


ADMIN_PREFIX = re.compile(
    r"^(?:(?:phuong|ward|xa|commune|quan|district|huyen|thanh pho|city|tinh|province|tp|p|q|w)\b|(?:q|p|w|d)\.?\s*\d)",
    re.I,
)


def constraints(area, address=""):
    streets, administrative = [], []
    pieces = split_parts(area)
    candidate, confident, _ = street_component(address)
    for index, part in enumerate(pieces):
        if STREET_PREFIX.match(part):
            streets.append(street_name(part))
        elif (
            index == 0
            and len(pieces) >= 2
            and not ADMIN_PREFIX.match(normalized(part))
            and confident
            and candidate == street_name(part)
            and canonical(part) not in admin_components(administrative_address(address))
        ):
            # Accept a bare leading road name only with evidence from the
            # address itself. Explicit ward/district labels stay administrative.
            streets.append(street_name(part))
        elif canonical(part):
            administrative.append(canonical(part))
    return streets, administrative


def street_component(address):
    pieces = split_parts(address)
    if not pieces:
        return "", False, 0
    index = 1 if HOUSE_ONLY.fullmatch(normalized(pieces[0])) and len(pieces) > 1 else 0
    text = pieces[index].strip()
    alley = bool(re.match(r"^(?:hẻm|hem|alley)\s+", text, re.I))
    text = re.sub(r"^(?:hẻm|hem|alley)\s+", "", text, flags=re.I)
    house = HOUSE.match(text)
    if house:
        text = text[house.end() :]
        text = re.sub(r"^(?:hẻm|hem|alley)\s+", "", text, flags=re.I)
    labelled = bool(STREET_PREFIX.match(text))
    return street_name(text), bool(house or labelled or alley or index), index + 1


def street_matches(address, wanted):
    candidate, _, _ = street_component(address)
    return candidate == wanted


def administrative_address(address, force_street=False):
    pieces = split_parts(address)
    _, confident, used = street_component(address)
    if confident or force_street:
        return ", ".join(pieces[used:])
    return address


def is_district7(area):
    text = canonical(area)
    return contains(text, "quan7") and contains(text, "hochiminh")


# Only wards wholly within a former district can prove membership without
# coordinates. Bình Hưng Hòa crosses the former Tân Phú boundary, so it is
# intentionally absent. Sources: Resolution 1685, clauses 18–21 and 62–66.
DISTRICT_WARDS = {
    "quan7": {"tan thuan", "phu thuan", "tan my", "tan hung"},
    "quantanphu": {"tay thanh", "tan son nhi", "phu tho hoa", "tan phu", "phu thanh"},
}


def admin_matches(address, area):
    components = admin_components(address)
    parts = parts_of(area)
    if not parts:
        return False
    if all(part in components for part in parts):
        return True
    # Match administrative components, never a street named after a ward.
    query = canonical(area)
    for district, wards in DISTRICT_WARDS.items():
        if not (contains(query, district) and contains(query, "hochiminh")):
            continue
        if "hochiminh" in components and components.intersection(wards):
            pattern = r"\b(?:" + district + r"|hochiminh|vietnam)\b"
            remaining = [re.sub(pattern, "", part).strip() for part in parts]
            return all(not part or part in components for part in remaining)
    return False


def text_matches(address, area):
    streets, parts = constraints(area, address)
    if not streets and not parts:
        return False
    if not all(street_matches(address, street) for street in streets):
        return False
    suffix = administrative_address(address, force_street=bool(streets))
    return not parts or admin_matches(suffix, ",".join(parts))


def place_coordinates(url):
    # /@lat,lon is viewport centre, NOT necessarily the selected business.
    matches = re.findall(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)", unquote(url))
    if not matches:
        return None
    lat, lon = map(float, matches[-1])
    return (lon, lat) if -90 <= lat <= 90 and -180 <= lon <= 180 else None


def in_ring(point, ring):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        x1, y1 = a[:2]
        x2, y2 = b[:2]
        cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
        if (
            abs(cross) <= 1e-12
            and min(x1, x2) - 1e-12 <= x <= max(x1, x2) + 1e-12
            and min(y1, y2) - 1e-12 <= y <= max(y1, y2) + 1e-12
        ):
            return True
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def in_geometry(point, geometry):
    polygons = (
        [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    )
    return any(
        poly and in_ring(point, poly[0]) and not any(in_ring(point, hole) for hole in poly[1:])
        for poly in polygons
    )


@lru_cache(maxsize=1)
def district7_boundary():
    return json.loads(
        (Path(__file__).parent / "data" / "hcm-district-7.geojson").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def tan_thuan_boundary():
    return json.loads(
        (Path(__file__).parent / "data" / "hcm-tan-thuan.geojson").read_text(encoding="utf-8")
    )


@lru_cache(maxsize=1)
def tan_phu_district_boundary():
    return json.loads(
        (Path(__file__).parent / "data" / "hcm-tan-phu-district.geojson").read_text(
            encoding="utf-8"
        )
    )


class AreaMatcher:
    def __init__(self, area):
        self.area = area
        self.streets, self.parts = constraints(area)
        self.boundary, self.covered, self.boundary_label = self.select_boundary(self.parts)

    @staticmethod
    def select_boundary(parts):
        administrative = " ".join(parts)
        if "tan thuan" in parts and "hochiminh" in parts:
            return (
                tan_thuan_boundary(),
                {"quan7", "hochiminh", "vietnam", "tan thuan"},
                "phường Tân Thuận",
            )
        elif is_district7(administrative):
            return district7_boundary(), {"quan7", "hochiminh", "vietnam"}, "Quận 7 cũ"
        elif contains(administrative, "quantanphu") and contains(administrative, "hochiminh"):
            return (
                tan_phu_district_boundary(),
                {"quantanphu", "hochiminh", "vietnam"},
                "quận Tân Phú cũ",
            )
        return None, set(), ""

    def matches(self, address, url=""):
        return self.evaluate(address, url)[0]

    def evaluate(self, address, url=""):
        streets, parts = constraints(self.area, address)
        if not streets and not parts:
            return False, "Khu vực trống."
        if not all(street_matches(address, street) for street in streets):
            return False, "Chưa khớp tên đường đã chọn."
        suffix = administrative_address(address, force_street=bool(streets))
        point = place_coordinates(url)
        boundary, covered, boundary_label = self.select_boundary(parts)
        if boundary and point:
            if not in_geometry(point, boundary["geometry"]):
                return False, "Tọa độ nằm ngoài " + boundary_label + "."
            residual = []
            pattern = (
                r"\b(?:"
                + "|".join(re.escape(p) for p in sorted(covered, key=len, reverse=True))
                + r")\b"
            )
            for part in parts:
                remaining = re.sub(r"\s+", " ", re.sub(pattern, "", part)).strip()
                if remaining:
                    residual.append(remaining)
            if all(remaining in admin_components(suffix) for remaining in residual):
                return True, ""
            return False, "Chưa khớp phần phường/khu vực chi tiết đã chọn."
        if not parts or admin_matches(suffix, ",".join(parts)):
            return True, ""
        return False, "Chưa khớp phường/thành phố đã chọn."

    @property
    def city_label(self):
        pieces = [p for p in split_parts(self.area) if canonical(p) != "vietnam"]
        if not pieces or STREET_PREFIX.match(pieces[-1]):
            return ""
        if canonical(pieces[-1]) == "hochiminh":
            return "Hồ Chí Minh"
        return re.sub(
            r"^(?:thành phố|thanh pho|tp\.?|city of|city|tỉnh|tinh|province)\s+",
            "",
            pieces[-1],
            flags=re.I,
        )

    def city_for(self, address):
        if self.city_label == "Hồ Chí Minh":
            return self.city_label
        pieces = [p for p in split_parts(address) if canonical(p) != "vietnam"]
        if len(pieces) < 2:
            return self.city_label
        return AreaMatcher(re.sub(r"\s+\d{5,6}$", "", pieces[-1])).city_label
