import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


TAX_LABEL = re.compile(
    r"(?:mã\s*số\s*(?:thuế(?:\s*(?:doanh\s*nghiệp|dn))?|doanh\s*nghiệp|đơn\s*vị)"
    r"|\bMST\b|tax\s*(?:code|id|number)|vat\s*(?:id|no\.?|number)?|\bTIN\b)",
    re.I,
)
LABELED_TAX_CODE = re.compile(
    r"(?:mã\s*số\s*(?:thuế(?:\s*(?:doanh\s*nghiệp|dn))?|doanh\s*nghiệp|đơn\s*vị)"
    r"|\bMST\b|tax\s*(?:code|id|number)|vat\s*(?:id|no\.?|number)?|\bTIN\b)"
    r"\s*[:：#\-]?\s*"
    r"(?P<number>\d(?:[\s.\-]?\d){9}"
    r"(?:\s*[\-–.]?\s*\d(?:[\s.\-]?\d){2})?)"
    r"(?![\d\s.\-]*\d)",
    re.I,
)


def normalize_tax_code(value):
    """Return a plausible Vietnamese tax code without inventing missing digits."""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits if len(digits) in (10, 13) else ""


def structured_tax_code(node):
    for key in ("taxID", "taxId", "vatID", "vatId", "vatNumber"):
        code = normalize_tax_code(node.get(key))
        if code:
            return code

    identifiers = node.get("identifier", [])
    if isinstance(identifiers, dict):
        identifiers = [identifiers]
    if isinstance(identifiers, list):
        for identifier in identifiers:
            if not isinstance(identifier, dict):
                continue
            label = " ".join(
                str(identifier.get(key, ""))
                for key in ("propertyID", "name", "@type")
            )
            if TAX_LABEL.search(label):
                code = normalize_tax_code(
                    identifier.get("value", identifier.get("identifier", ""))
                )
                if code:
                    return code
    return ""


def extract_website(html, url):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript"]):
        if node.name != "script" or node.get("type") != "application/ld+json":
            node.decompose()
    result = {}
    for anchor in soup.select('a[href^="tel:"]'):
        number = anchor.get("href", "")[4:].split("?")[0].strip()
        if 9 <= len(re.sub(r"\D", "", number)) <= 15:
            result.setdefault("phone", number)
    for anchor in soup.select('a[href^="mailto:"]'):
        email = anchor.get("href", "")[7:].split("?")[0].strip()
        if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            result.setdefault("email", email)
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in list(nodes):
            if isinstance(node, dict) and isinstance(node.get("@graph"), list):
                nodes.extend(node["@graph"])
        for node in nodes:
            if not isinstance(node, dict):
                continue
            for source, target in (
                ("telephone", "phone"),
                ("email", "email"),
                ("legalName", "legal_name"),
            ):
                if isinstance(node.get(source), str):
                    result.setdefault(target, node[source].strip())
            if "tax_code" not in result:
                code = structured_tax_code(node)
                if code:
                    result["tax_code"] = code
    text = soup.get_text(" ", strip=True)
    if "tax_code" not in result:
        match = LABELED_TAX_CODE.search(text)
        if match:
            code = normalize_tax_code(match.group("number"))
            if code:
                result["tax_code"] = code
    links = []
    for anchor in soup.select("a[href]"):
        try:
            href = urljoin(url, anchor.get("href", ""))
            parts = urlsplit(href)
            if parts.username or parts.password or parts.port not in (None, 80, 443):
                continue
        except ValueError:
            continue
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https"):
            continue
        if host in ("facebook.com", "www.facebook.com", "fb.com"):
            result.setdefault("facebook", href)
        if host == "zalo.me":
            result.setdefault("zalo", href)
        if parts.netloc == urlsplit(url).netloc and re.search(
            r"lien[-_]?he|contact|gioi[-_]?thieu|about|doanh[-_]?nghiep|"
            r"thong[-_]?tin|tax|legal|company|business|ma[-_]?so[-_]?thue",
            parts.path,
            re.I,
        ):
            links.append(href.split("#")[0])
    return result, list(dict.fromkeys(links))[:2]
