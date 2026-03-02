from datetime import datetime

from pydantic import BaseModel

from app.models import SyncRunStatus


class SyncRunBase(BaseModel):
    source: str
    status: SyncRunStatus = SyncRunStatus.running


class SyncRunCreate(SyncRunBase):
    source_id: str | None = None  # Resolved from source entity during compatibility window


class SyncRunRead(SyncRunBase):
    id: str
    source_id: str | None  # Exposed during migration window; will be non-null after enforcement
    started_at: datetime
    finished_at: datetime | None
    fetched_count: int
    mapped_count: int
    unique_count: int
    deduped_by_external_id: int
    deduped_by_apply_url: int
    inserted_count: int
    updated_count: int
    closed_count: int
    failed_count: int
    error_summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SyncRunUpdate(BaseModel):
    status: SyncRunStatus | None = None
    finished_at: datetime | None = None
    fetched_count: int | None = None
    mapped_count: int | None = None
    unique_count: int | None = None
    deduped_by_external_id: int | None = None
    deduped_by_apply_url: int | None = None
    inserted_count: int | None = None
    updated_count: int | None = None
    closed_count: int | None = None
    failed_count: int | None = None
    error_summary: str | None = None
