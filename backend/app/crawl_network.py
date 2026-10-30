"""Bounded, DNS-pinned HTTP for untrusted restaurant websites."""

import http.client
import ipaddress
import socket
import ssl
from urllib.parse import quote, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

AGENT = "LeadFinder/0.2 (business-contact-research)"


class FetchError(ValueError):
    pass


def public_target(url):
    try:
        parts = urlsplit(url)
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if (
            parts.scheme not in ("http", "https")
            or not parts.hostname
            or parts.username
            or parts.password
            or port not in (80, 443)
        ):
            raise FetchError("URL hoặc cổng truy cập không được hỗ trợ.")
        hostname = parts.hostname.encode("idna").decode()
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise FetchError("Không truy cập địa chỉ nội bộ.")
        addresses = {a[4][0] for a in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
            raise FetchError("Không truy cập địa chỉ mạng riêng hoặc địa chỉ hệ thống.")
        return parts, hostname, port, sorted(addresses)[0]
    except FetchError:
        raise
    except OSError:
        raise FetchError("Không phân giải được tên miền website.") from None
    except ValueError:
        raise FetchError("URL website không hợp lệ.") from None


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, hostname, port, ip):
        super().__init__(hostname, port, timeout=12, context=ssl.create_default_context())
        self.pinned_ip = ip

    def connect(self):
        sock = socket.create_connection((self.pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def fetch(url, max_bytes=2_000_000, before_request=None):
    for _ in range(5):
        if before_request:
            before_request(url)
        parts, hostname, port, ip = public_target(url)
        conn = (
            PinnedHTTPS(hostname, port, ip)
            if parts.scheme == "https"
            else http.client.HTTPConnection(ip, port, timeout=12)
        )
        try:
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            path = quote(path, safe="/?&=%:@+;,-._~")
            conn.request(
                "GET",
                path,
                headers={
                    "Host": hostname,
                    "User-Agent": AGENT,
                    "Accept": "text/html,text/plain;q=0.8",
                    "Accept-Encoding": "identity",
                },
            )
            response = conn.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                location = response.getheader("Location")
                if not location:
                    raise FetchError("Chuyển hướng thiếu địa chỉ đích.")
                url = urljoin(url, location)
                continue
            if response.status >= 400:
                return response.status, "", url
            content_type = response.getheader("Content-Type", "")
            if not any(t in content_type.lower() for t in ("text/", "application/xhtml")):
                raise FetchError("Website không trả nội dung văn bản.")
            data = response.read(max_bytes + 1)
            if len(data) > max_bytes:
                raise FetchError("Trang vượt giới hạn kích thước.")
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                decoded = data.decode(charset, errors="replace")
            except LookupError:
                decoded = data.decode("utf-8", errors="replace")
            return (
                response.status,
                decoded,
                url,
            )
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError("Không đọc được website: " + type(exc).__name__) from None
        finally:
            conn.close()
    raise FetchError("Website chuyển hướng quá nhiều lần.")


def robots_allowed(url, cache):
    parts = urlsplit(url)
    root = parts.scheme + "://" + parts.netloc
    if root not in cache:
        status, body, _ = fetch(root + "/robots.txt", max_bytes=200_000)
        if status in (404, 410):
            cache[root] = None
        elif status == 200:
            parser = RobotFileParser()
            parser.parse(body.splitlines())
            cache[root] = parser
        else:
            raise FetchError("Chưa đọc được robots.txt; bỏ qua website trong lượt này.")
    return cache[root] is None or cache[root].can_fetch(AGENT, url)


def require_robots(url, cache):
    if not robots_allowed(url, cache):
        raise FetchError("Website không cho phép thu thập theo robots.txt.")
