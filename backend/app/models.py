import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def uid():
    return str(uuid.uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    csrf: Mapped[str] = mapped_column(String(100))
    expires: Mapped[str] = mapped_column(String(50))


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    allow_store: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_export: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_display: Mapped[bool] = mapped_column(Boolean, default=False)


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (
        Index("ix_locations_updated", "updated_at", "id"),
        Index("ix_locations_city_status", "city", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    identity_key: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(150), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    phone: Mapped[str] = mapped_column(String(150), default="")
    website: Mapped[str] = mapped_column(Text, default="")
    tax_code: Mapped[str] = mapped_column(String(50), default="")
    tax_status: Mapped[str] = mapped_column(String(30), default="unverified")
    status: Mapped[str] = mapped_column(String(30), default="new")
    notes: Mapped[str] = mapped_column(Text, default="")
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint(
            "location_id", "field", "value", "source_id", "source_ref", name="uq_observation"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"), index=True)
    field: Mapped[str] = mapped_column(String(50))
    value: Mapped[str] = mapped_column(Text)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    source_ref: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    filename: Mapped[str] = mapped_column(String(200))
    rows: Mapped[list] = mapped_column(JSON)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class Audit(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str] = mapped_column(String(100))
    changes: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50), default=now)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    key: Mapped[str] = mapped_column(String(150), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    reset_at: Mapped[str] = mapped_column(String(50))


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    keyword: Mapped[str] = mapped_column(String(150))
    area: Mapped[str] = mapped_column(String(150))
    target: Mapped[int] = mapped_column(Integer)
    enrich_website: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    message: Mapped[str] = mapped_column(Text, default="Đang chờ thu thập.")
    discovery_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    run_token: Mapped[str] = mapped_column(String(64), default="")
    heartbeat: Mapped[str] = mapped_column(String(50), default=now)
    created_at: Mapped[str] = mapped_column(String(50), default=now)
    updated_at: Mapped[str] = mapped_column(String(50), default=now)


class CrawlControl(Base):
    __tablename__ = "crawl_control"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    active_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CrawlEntry(Base):
    __tablename__ = "crawl_entries"
    __table_args__ = (UniqueConstraint("job_id", "external_key", name="uq_job_place"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("crawl_jobs.id"), index=True)
    external_key: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(300), default="")
    state: Mapped[str] = mapped_column(String(30), default="pending")
    location_id: Mapped[str | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ExternalPlace(Base):
    __tablename__ = "external_places"
    external_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    location_id: Mapped[str] = mapped_column(ForeignKey("locations.id"))
