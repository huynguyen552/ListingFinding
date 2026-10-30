import json
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup


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
    text = soup.get_text(" ", strip=True)
    match = re.search(
        r"(?:mã\s*số\s*thuế|mã\s*số\s*doanh\s*nghiệp|\bMST\b|tax\s*(?:code|id))\s*[:：\-]?\s*(\d{10}(?:[-\s]?\d{3})?)(?!\d|[-\s]+\d)",
        text,
        re.I,
    )
    if match:
        result["tax_code"] = re.sub(r"[^0-9]", "", match.group(1))
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
            r"lien[-_]?he|contact|gioi[-_]?thieu|about", parts.path, re.I
        ):
            links.append(href.split("#")[0])
    return result, list(dict.fromkeys(links))[:2]
