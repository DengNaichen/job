import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Index, String, text
from sqlmodel import Field, SQLModel


class SyncRunStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class SyncRun(SQLModel, table=True):
    __table_args__ = (
        Index(
            "uq_syncrun_running_source_id",
            "source_id",
            unique=True,
            postgresql_where=text("status = 'running' AND source_id IS NOT NULL"),
            sqlite_where=text("status = 'running' AND source_id IS NOT NULL"),
        ),
    )

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    # Authoritative owner FK — nullable during migration window; enforced NOT NULL in second revision.
    source_id: str | None = Field(
        default=None,
        sa_column=Column(
            String(36), ForeignKey("sources.id", ondelete="RESTRICT"), nullable=True, index=True
        ),
    )
    # Compatibility source key (legacy string). Preserved throughout migration.
    source: str = Field(index=True)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = Field(default=None)
    status: SyncRunStatus

    fetched_count: int = Field(default=0)
    mapped_count: int = Field(default=0)
    unique_count: int = Field(default=0)
    deduped_by_external_id: int = Field(default=0)
    deduped_by_apply_url: int = Field(default=0)
    inserted_count: int = Field(default=0)
    updated_count: int = Field(default=0)
    closed_count: int = Field(default=0)
    failed_count: int = Field(default=0)

    error_summary: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
