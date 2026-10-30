from sqlalchemy import case, func, select

from .models import CrawlEntry


def crawl_counts(db, job_id):
    rows = db.execute(
        select(
            CrawlEntry.state,
            func.count(),
            func.count(func.distinct(func.coalesce(CrawlEntry.location_id, CrawlEntry.id))),
            func.sum(case((CrawlEntry.error != "", 1), else_=0)),
        )
        .where(CrawlEntry.job_id == job_id)
        .group_by(CrawlEntry.state)
    ).all()
    counts = {state: unique if state == "done" else total for state, total, unique, _ in rows}
    found = sum(total for _, total, _, _ in rows)
    warnings = sum(warnings for state, _, _, warnings in rows if state == "done")
    return counts, found, warnings
