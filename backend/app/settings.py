import os
from urllib.parse import urlsplit


def database_url(value):
    for prefix in ("postgres://", "postgresql://"):
        if value.startswith(prefix):
            return "postgresql+psycopg://" + value[len(prefix) :]
    return value


def allowed_hosts():
    hosts = {"localhost", "127.0.0.1", "api", "testserver"}
    hosts.update(h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip())
    if os.getenv("RENDER_EXTERNAL_HOSTNAME"):
        hosts.add(os.environ["RENDER_EXTERNAL_HOSTNAME"])
    return sorted(hosts)


def allowed_origins():
    origins = {
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    }
    external = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if external and urlsplit(external).scheme == "https":
        origins.add(external)
    return origins
