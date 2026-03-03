import enum
import uuid
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.source import Source

from sqlalchemy import Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import DateTime
from sqlmodel import Field, SQLModel, Relationship

from app.models.job_location import JobLocation


class JobStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class WorkplaceType(str, enum.Enum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unknown = "unknown"


class Job(SQLModel, table=True):
    __table_args__ = (
        # ix_job_source_id_status_last_seen_at is created by the Alembic migration (Phase 2).
        # Do NOT re-declare it here — SQLModel.metadata.create_all (used in tests) would
        # try to create it again and conflict with the migration-managed index.
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    # Authoritative owner FK — nullable during migration window; enforced NOT NULL in second revision.
    source_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(36), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
    )
    external_job_id: str = Field(index=True)
    title: str
    apply_url: str
    normalized_apply_url: str | None = Field(default=None, index=True)
    content_fingerprint: str | None = Field(default=None, index=True)
    dedupe_group_id: str | None = Field(default=None, index=True)
    status: JobStatus = Field(default=JobStatus.open, index=True)

    department: str | None = Field(default=None)
    team: str | None = Field(default=None)
    employment_type: str | None = Field(default=None)

    description_html_key: str | None = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    description_html_hash: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    description_plain: str | None = Field(default=None)

    sponsorship_not_available: str = Field(default="unknown", index=True)
    job_domain_raw: str | None = Field(default=None)
    job_domain_normalized: str = Field(default="unknown", index=True)
    min_degree_level: str = Field(default="unknown", index=True)
    min_degree_rank: int = Field(default=-1, index=True)
    structured_jd_version: int = Field(default=3, index=True)

    published_at: datetime | None = Field(default=None, index=True)
    source_updated_at: datetime | None = Field(default=None)
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    raw_payload_key: str | None = Field(default=None, sa_column=Column(String(255), nullable=True))
    raw_payload_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))

    # LLM 提取的结构化 JD 信息
    structured_jd: dict[str, Any] | None = Field(default=None, sa_column=Column(JSONB()))
    structured_jd_updated_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    source_record: "Source" = Relationship()
    job_locations: list[JobLocation] = Relationship(back_populates="job")
