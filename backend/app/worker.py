import os

from celery import Celery

from .queueing import collect_work

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
    for job_id in collect_work():
        crawl.delay(job_id)
