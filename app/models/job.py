import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel


class JobStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class Job(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("source", "external_job_id", name="uq_job_source_external_job_id"),
        Index("ix_job_source_status_last_seen_at", "source", "status", "last_seen_at"),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    source: str = Field(index=True)
    external_job_id: str = Field(index=True)
    title: str
    apply_url: str
    normalized_apply_url: str | None = Field(default=None, index=True)
    content_fingerprint: str | None = Field(default=None, index=True)
    dedupe_group_id: str | None = Field(default=None, index=True)
    status: JobStatus = Field(default=JobStatus.open, index=True)

    location_text: str | None = Field(default=None)
    department: str | None = Field(default=None)
    team: str | None = Field(default=None)
    employment_type: str | None = Field(default=None)

    description_html: str | None = Field(default=None)
    description_html_key: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    description_html_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    description_plain: str | None = Field(default=None)
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(1024), nullable=True))
    embedding_model: str | None = Field(default=None, sa_column=Column(String(128), nullable=True))
    embedding_updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    sponsorship_not_available: str = Field(default="unknown", index=True)
    job_domain_raw: str | None = Field(default=None)
    job_domain_normalized: str = Field(default="unknown", index=True)
    min_degree_level: str = Field(default="unknown", index=True)
    min_degree_rank: int = Field(default=-1, index=True)
    structured_jd_version: int = Field(default=3, index=True)

    published_at: datetime | None = Field(default=None, index=True)
    source_updated_at: datetime | None = Field(default=None)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB()))
    raw_payload_key: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    raw_payload_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))

    # LLM 提取的结构化 JD 信息
    structured_jd: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB()))
    structured_jd_updated_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
