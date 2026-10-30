"""Single PostgreSQL-backed collector for the constrained Render instance."""

import logging
import signal

from .crawling import run_crawl
from .queueing import collect_work, shutdown_requested


def main():
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *a: shutdown_requested.set())
    while not shutdown_requested.is_set():
        try:
            for job_id in collect_work():
                if shutdown_requested.is_set():
                    break
                run_crawl(job_id)
        except Exception:
            logging.getLogger("leadfinder").exception("Collector queue check failed")
        shutdown_requested.wait(3)


if __name__ == "__main__":
    main()
