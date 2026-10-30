from urllib.parse import urlsplit

import pytest

from app import crawl_network as network


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (404, "", True),
        (410, "", True),
        (200, "User-agent: *\nDisallow: /private", False),
        (200, "User-agent: *\nDisallow: /other", True),
    ],
)
def test_robots_policy_and_cache(monkeypatch, status, body, expected):
    calls = []
    monkeypatch.setattr(
        network, "fetch", lambda *a, **k: calls.append(a[0]) or (status, body, a[0])
    )
    cache = {}
    for _ in range(2):
        assert network.robots_allowed("https://example.com/private", cache) is expected
    assert calls == ["https://example.com/robots.txt"]


def test_robots_unavailable_is_not_permission(monkeypatch):
    monkeypatch.setattr(network, "fetch", lambda *a, **k: (503, "", a[0]))
    with pytest.raises(network.FetchError):
        network.require_robots("https://example.com", {})


def test_redirect_is_checked_before_fetching_destination(monkeypatch):
    monkeypatch.setattr(
        network, "public_target", lambda url: (urlsplit(url), "example.com", 80, "1.1.1.1")
    )
    opened = []

    class Connection:
        def __init__(self, *a, **k):
            opened.append(self)

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return self

        status = 302

        def getheader(self, name):
            return "http://other.example/private"

        def close(self):
            pass

    monkeypatch.setattr(network.http.client, "HTTPConnection", Connection)
    checked = []

    def permission(url):
        checked.append(url)
        if "other.example" in url:
            raise network.FetchError("robots denied destination")

    with pytest.raises(network.FetchError, match="robots denied"):
        network.fetch("http://example.com", before_request=permission)
    assert checked == ["http://example.com", "http://other.example/private"]
    assert len(opened) == 1


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://example.com:9000",
        "http://[broken",
    ],
)
def test_invalid_website_rejected(url):
    with pytest.raises(network.FetchError):
        network.public_target(url)
