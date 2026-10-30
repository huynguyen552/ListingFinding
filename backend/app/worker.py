import os
from datetime import datetime, timedelta, timezone

from celery import Celery
from sqlalchemy import select

from .db import SessionLocal
from .models import CrawlControl, CrawlJob, now

celery = Celery("leadfinder", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=3,
    broker_transport_options={"socket_connect_timeout": 2, "socket_timeout": 2},
    beat_schedule={"recover-and-dispatch": {"task": "crawl.dispatch", "schedule": 15.0}},
)


@celery.task(name="crawl.run", soft_time_limit=3600, time_limit=3660)
def crawl(job_id):
    from .crawling import run_crawl

    run_crawl(job_id)


@celery.task(name="crawl.dispatch")
def dispatch():
    queued = []
    with SessionLocal() as db:
        control = db.scalar(select(CrawlControl).where(CrawlControl.id == 1).with_for_update())
        jobs = db.scalars(
            select(CrawlJob)
            .where(CrawlJob.status.in_(["queued", "running", "pausing", "cancelling"]))
            .with_for_update()
        ).all()
        for job in jobs:
            stale = datetime.fromisoformat(job.heartbeat) < datetime.now(timezone.utc) - timedelta(
                minutes=4
            )
            if job.status == "queued":
                queued.append(job.id)
            elif stale:
                job.run_token = ""
                job.status = "cancelled" if job.status == "cancelling" else "paused"
                job.message = "Tác vụ bị ngắt. Kết quả đã lưu được giữ lại; có thể bấm Tiếp tục."
                job.updated_at = now()
                if control and control.active_job_id == job.id:
                    control.active_job_id = None
        db.commit()
    for job_id in queued:
        crawl.delay(job_id)
