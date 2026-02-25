import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class JobStatus(str, enum.Enum):
    open = "open"
    closed = "closed"


class Job(SQLModel, table=True):
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
    description_plain: str | None = Field(default=None)

    published_at: datetime | None = Field(default=None, index=True)
    source_updated_at: datetime | None = Field(default=None)
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON()))

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
