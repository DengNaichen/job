"""Structured JD persistence workflows."""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime, timezone

from app.models import Job
from app.repositories.job import JobRepository
from app.schemas.structured_jd import (
    BatchStructuredJDItem,
    build_structured_jd_projection,
    build_structured_jd_storage_payload,
)


class StructuredJDError(Exception):
    """Base exception for structured JD workflows."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class JobStructuredJDMappingError(StructuredJDError):
    """Raised when parsed structured JD items cannot map to input jobs."""

    def __init__(self, job_id: str):
        super().__init__(
            code="STRUCTURED_JD_MAPPING_ERROR",
            message=f"Parsed result missing job_id={job_id}",
        )
        self.job_id = job_id


class StructuredJDService:
    """Application service for structured JD read/write workflows."""

    def __init__(self, repository: JobRepository):
        self.repository = repository

    async def list_pending_jobs_for_parse(
        self,
        limit: int = 5,
        *,
        version_only: bool = False,
        exclude_job_ids: Collection[str] | None = None,
    ) -> list[Job]:
        """List jobs pending structured JD extraction."""
        if limit <= 0:
            raise ValueError("limit must be > 0")
        return await self.repository.list_pending_structured_jd(
            limit=limit,
            version_only=version_only,
            exclude_job_ids=exclude_job_ids,
        )

    async def persist_structured_jd_batch(
        self,
        jobs: list[Job],
        parsed_items: list[BatchStructuredJDItem],
    ) -> None:
        """Persist structured JD results onto the corresponding jobs."""
        if not jobs:
            return

        now = datetime.now(timezone.utc)
        now_naive = now.replace(tzinfo=None)
        parsed_by_job_id = {item.job_id: item.model_dump(mode="python") for item in parsed_items}

        for job in jobs:
            item_payload = parsed_by_job_id.get(str(job.id))
            if item_payload is None:
                raise JobStructuredJDMappingError(str(job.id))
            job.structured_jd = build_structured_jd_storage_payload(item_payload)
            projection = build_structured_jd_projection(item_payload)
            job.sponsorship_not_available = str(projection["sponsorship_not_available"])
            job.job_domain_raw = (
                projection["job_domain_raw"]
                if isinstance(projection["job_domain_raw"], str)
                else None
            )
            job.job_domain_normalized = str(projection["job_domain_normalized"])
            job.min_degree_level = str(projection["min_degree_level"])
            job.min_degree_rank = int(projection["min_degree_rank"])
            job.structured_jd_version = int(projection["structured_jd_version"])
            job.structured_jd_updated_at = now
            job.updated_at = now_naive

        await self.repository.save_all(jobs)
