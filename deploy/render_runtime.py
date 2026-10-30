"""One Render web instance: local queue, one crawler, beat and HTTP/static UI."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def process_commands(port):
    if os.getenv("QUEUE_MODE") == "database":
        return [
            ("crawler", [sys.executable, "-m", "app.render_worker"]),
            (
                "web",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(port),
                    "--workers",
                    "1",
                    "--no-proxy-headers",
                ],
            ),
        ]
    return [
        (
            "redis",
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--protected-mode",
                "yes",
                "--save",
                "",
                "--appendonly",
                "no",
                "--maxmemory",
                "32mb",
                "--maxmemory-policy",
                "noeviction",
            ],
        ),
        (
            "crawler",
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.worker.celery",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--loglevel=WARNING",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
            ],
        ),
        (
            "scheduler",
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.worker.celery",
                "beat",
                "--loglevel=WARNING",
                "--schedule=/tmp/leadfinder-beat",
            ],
        ),
        (
            "web",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(port),
                "--workers",
                "1",
                "--no-proxy-headers",
            ],
        ),
    ]


def stop_processes(processes, grace_seconds=20):
    # Stop accepting new jobs, then stop the crawler before its local broker.
    for name in ("web", "scheduler", "crawler", "redis"):
        process = dict(processes).get(name)
        if process and process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + grace_seconds
    for _, process in reversed(processes):
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def main():
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL must point to Render PostgreSQL, never local SQLite.")
    if not os.environ["DATABASE_URL"].startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        raise RuntimeError("Render requires persistent PostgreSQL.")
    port = int(os.getenv("PORT", "10000"))
    if not 1 <= port <= 65535:
        raise RuntimeError("Invalid PORT.")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, timeout=120)
    # Keep FastAPI/SQLAlchemy imports out of the long-lived supervisor process.
    subprocess.run([sys.executable, "-m", "app.bootstrap"], check=True, timeout=120)
    # Runtime disk is disposable. Crawl entries and queue checkpoints live in PG.
    Path("/tmp/leadfinder").mkdir(exist_ok=True)
    processes = []
    stopping = False

    def request_stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    code = 0
    try:
        for name, command in process_commands(port):
            processes.append((name, subprocess.Popen(command)))
        while not stopping:
            for name, process in processes:
                if process.poll() is not None:
                    print(
                        f"{name} exited; restarting the whole service.", file=sys.stderr, flush=True
                    )
                    code, stopping = 1, True
                    break
            time.sleep(0.5)
    finally:
        stop_processes(processes)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
