from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models import JobStatus, WorkplaceType


class JobBase(BaseModel):
    source: str
    external_job_id: str
    title: str
    apply_url: str
    normalized_apply_url: str | None = None
    status: JobStatus = JobStatus.open

    location_text: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country_code: str | None = None
    location_workplace_type: WorkplaceType = WorkplaceType.unknown
    location_remote_scope: str | None = None

    department: str | None = None
    team: str | None = None
    employment_type: str | None = None


class JobCreate(JobBase):
    source_id: str | None = (
        None  # Resolved by service from source string during compatibility window
    )
    content_fingerprint: str | None = None
    dedupe_group_id: str | None = None
    description_html: str | None = None
    description_plain: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    sponsorship_not_available: str = "unknown"
    job_domain_raw: str | None = None
    job_domain_normalized: str = "unknown"
    min_degree_level: str = "unknown"
    min_degree_rank: int = -1
    structured_jd_version: int = 3
    structured_jd: dict[str, Any] | None = None
    structured_jd_updated_at: datetime | None = None


class JobRead(JobBase):
    id: str
    source_id: str | None  # Exposed during migration window; will be non-null after enforcement
    content_fingerprint: str | None
    dedupe_group_id: str | None
    description_html: str | None
    description_html_key: str | None
    description_html_hash: str | None
    description_plain: str | None
    published_at: datetime | None
    source_updated_at: datetime | None
    raw_payload: dict[str, Any]
    raw_payload_key: str | None
    raw_payload_hash: str | None
    sponsorship_not_available: str
    job_domain_raw: str | None
    job_domain_normalized: str
    min_degree_level: str
    min_degree_rank: int
    structured_jd_version: int
    structured_jd: dict[str, Any] | None
    structured_jd_updated_at: datetime | None
    ingested_at: datetime
    last_seen_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobUpdate(BaseModel):
    apply_url: str | None = None
    normalized_apply_url: str | None = None
    content_fingerprint: str | None = None
    dedupe_group_id: str | None = None
    title: str | None = None
    status: JobStatus | None = None
    location_text: str | None = None
    location_city: str | None = None
    location_region: str | None = None
    location_country_code: str | None = None
    location_workplace_type: WorkplaceType | None = None
    location_remote_scope: str | None = None
    department: str | None = None
    team: str | None = None
    employment_type: str | None = None
    description_html: str | None = None
    description_plain: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    raw_payload: dict[str, Any] | None = None
    sponsorship_not_available: str | None = None
    job_domain_raw: str | None = None
    job_domain_normalized: str | None = None
    min_degree_level: str | None = None
    min_degree_rank: int | None = None
    structured_jd_version: int | None = None
    structured_jd: dict[str, Any] | None = None
    structured_jd_updated_at: datetime | None = None
