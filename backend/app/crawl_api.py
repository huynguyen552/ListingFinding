from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .area_matching import canonical
from .crawl_stats import crawl_counts
from .db import get_db
from .models import Audit, CrawlControl, CrawlEntry, CrawlJob, Location, Source, now
from .security import current_user

router = APIRouter(prefix="/api/v1/crawl-jobs", tags=["Thu thập dữ liệu"])


def job_view(db, job):
    counts, found, warnings = crawl_counts(db, job.id)
    view = {
        key: getattr(job, key)
        for key in (
            "id",
            "keyword",
            "area",
            "target",
            "enrich_website",
            "status",
            "message",
            "created_at",
            "updated_at",
        )
    } | {"counts": counts, "found": found, "warnings": warnings}
    if job.status == "completed" and not counts.get("done"):
        view["status"] = "no_results"
    if job.status in ("completed", "no_results") and counts.get("failed"):
        view["status"] = "completed_with_errors"
    return view


class StartCrawl(BaseModel):
    keyword: str = Field(min_length=2, max_length=150)
    area: str = Field(min_length=2, max_length=150)
    target: int = Field(20, ge=1, le=200)
    enrich_website: bool = True
    request_key: str = Field(min_length=16, max_length=64)


@router.post("", status_code=202)
def start(body: StartCrawl, user=Depends(current_user), db: Session = Depends(get_db)):
    keyword, area = body.keyword.strip(), body.area.strip()
    if len(keyword) < 2 or len(area) < 2 or not canonical(keyword) or not canonical(area):
        raise HTTPException(422, "Nhập từ khóa và khu vực cần tìm.")
    control = db.scalar(select(CrawlControl).where(CrawlControl.id == 1).with_for_update())
    if not control:
        raise HTTPException(503, "Migration của bộ thu thập chưa hoàn tất.")
    previous = db.scalar(select(CrawlJob).where(CrawlJob.request_key == body.request_key))
    if previous:
        return job_view(db, previous)
    if control.active_job_id:
        raise HTTPException(409, "Đang có một đợt thu thập. Hãy tạm dừng hoặc chờ hoàn thành.")
    source = db.get(Source, "google_maps")
    if not source or not source.allow_store:
        raise HTTPException(403, "Nguồn Google Maps hiện chưa được bật để lưu dữ liệu.")
    job = CrawlJob(
        user_id=user.id,
        request_key=body.request_key,
        keyword=keyword,
        area=area,
        target=body.target,
        enrich_website=body.enrich_website,
    )
    db.add(job)
    db.flush()
    control.active_job_id = job.id
    db.add(
        Audit(
            user_id=user.id,
            action="start_crawl",
            entity_id=job.id,
            changes={"keyword": keyword, "area": area, "target": body.target},
        )
    )
    db.commit()
    # Commit first. Dispatcher retries queued jobs if the broker is temporarily offline.
    try:
        from .worker import crawl

        crawl.apply_async(args=[job.id], retry=False)
    except Exception:
        pass
    return job_view(db, job)


@router.get("")
def jobs(user=Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(CrawlJob).order_by(CrawlJob.created_at.desc()).limit(30)).all()
    return {"items": [job_view(db, job) for job in rows]}


@router.get("/{job_id}")
def job_detail(job_id: str, user=Depends(current_user), db: Session = Depends(get_db)):
    job = db.get(CrawlJob, job_id)
    if not job:
        raise HTTPException(404, "Không tìm thấy đợt thu thập.")
    entries = db.execute(
        select(CrawlEntry, Location)
        .outerjoin(Location, CrawlEntry.location_id == Location.id)
        .where(CrawlEntry.job_id == job.id)
        .order_by(CrawlEntry.id)
        .limit(200)
    ).all()
    from .crawling import source_url
    from .main import display_sources, location_view

    allowed = display_sources(db)
    return {
        **job_view(db, job),
        "entries": [
            {
                "id": entry.id,
                "state": entry.state,
                "error": entry.error,
                "name": entry.name,
                "source_url": source_url(entry.url),
                "address": ((entry.raw_data or {}).get("values") or {}).get("address", ""),
                "location": location_view(place, allowed) if place else None,
            }
            for entry, place in entries
        ],
    }


@router.post("/{job_id}/{action}")
def control_job(
    job_id: str, action: str, user=Depends(current_user), db: Session = Depends(get_db)
):
    if action not in ("pause", "resume", "cancel", "retry-area"):
        raise HTTPException(404, "Thao tác không được hỗ trợ.")
    control = db.scalar(select(CrawlControl).where(CrawlControl.id == 1).with_for_update())
    job = db.scalar(select(CrawlJob).where(CrawlJob.id == job_id).with_for_update())
    if not job or not control:
        raise HTTPException(404, "Không tìm thấy đợt thu thập.")
    if action == "retry-area":
        if job.status in ("running", "queued", "pausing", "cancelling"):
            raise HTTPException(
                409, "Hãy tạm dừng hoặc chờ đợt hiện tại kết thúc trước khi kiểm tra lại."
            )
        if control.active_job_id and control.active_job_id != job.id:
            raise HTTPException(409, "Đang có một đợt khác chạy.")
        skipped = db.scalars(
            select(CrawlEntry).where(
                CrawlEntry.job_id == job.id,
                CrawlEntry.state == "skipped",
                CrawlEntry.error.startswith("Địa chỉ chưa khớp khu vực"),
            )
        ).all()
        if not skipped:
            raise HTTPException(409, "Không có địa điểm bị bỏ qua do khu vực để kiểm tra lại.")
        for entry in skipped:
            entry.state, entry.error = "pending", ""
        job.run_token = ""
        job.status, job.message, job.heartbeat = (
            "queued",
            f"Đang kiểm tra lại khu vực cho {len(skipped)} địa điểm đã tìm thấy…",
            now(),
        )
        control.active_job_id = job.id
    elif action == "resume":
        if job_view(db, job)["status"] not in (
            "paused",
            "blocked",
            "failed",
            "completed_with_errors",
        ):
            raise HTTPException(409, "Đợt này chưa thể tiếp tục.")
        if control.active_job_id and control.active_job_id != job.id:
            raise HTTPException(409, "Đang có một đợt khác chạy.")
        failed_entries = db.scalars(
            select(CrawlEntry).where(CrawlEntry.job_id == job.id, CrawlEntry.state == "failed")
        ).all()
        for entry in failed_entries:
            entry.state, entry.error = "pending", ""
        job.run_token = ""
        job.status, job.message, job.heartbeat = "queued", "Đang chờ tiếp tục…", now()
        control.active_job_id = job.id
    elif action == "pause":
        if job.status not in ("running", "queued"):
            raise HTTPException(409, "Đợt này không đang chạy.")
        job.status = "paused" if job.status == "queued" else "pausing"
        job.message = "Đang tạm dừng; chờ thao tác đang chạy kết thúc…"
        if job.status == "paused":
            control.active_job_id = None
    else:
        if job.status in ("completed", "cancelled"):
            raise HTTPException(409, "Đợt này đã kết thúc.")
        job.status = "cancelling" if job.status in ("running", "pausing") else "cancelled"
        job.message = "Đang hủy…" if job.status == "cancelling" else "Đã hủy; giữ kết quả đã lưu."
        if job.status == "cancelled" and control.active_job_id == job.id:
            control.active_job_id = None
    job.updated_at = now()
    db.add(
        Audit(
            user_id=user.id,
            action=action + "_crawl",
            entity_id=job.id,
            changes={"status": job.status},
        )
    )
    db.commit()
    return job_view(db, job)
