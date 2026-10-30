from datetime import datetime, timedelta, timezone
from threading import Event

from sqlalchemy import select

from .db import SessionLocal
from .models import CrawlControl, CrawlJob, now

shutdown_requested = Event()


def collect_work():
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
    return queued
