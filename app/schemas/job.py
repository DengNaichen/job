from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import JobStatus


class JobBase(BaseModel):
    source: str
    external_job_id: str
    title: str
    apply_url: str
    normalized_apply_url: str | None = None
    status: JobStatus = JobStatus.open
    location_text: str | None = None
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None


class JobCreate(JobBase):
    content_fingerprint: str | None = None
    dedupe_group_id: str | None = None
    description_html: str | None = None
    description_plain: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    raw_payload: dict[str, Any] = {}


class JobRead(JobBase):
    id: str
    content_fingerprint: str | None
    dedupe_group_id: str | None
    description_html: str | None
    description_plain: str | None
    published_at: datetime | None
    source_updated_at: datetime | None
    ingested_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobUpdate(BaseModel):
    title: str | None = None
    status: JobStatus | None = None
    location_text: str | None = None
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None
    description_html: str | None = None
    description_plain: str | None = None
    source_updated_at: datetime | None = None
