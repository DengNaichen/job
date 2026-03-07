"""JD service for extraction orchestration and structured JD persistence."""

from __future__ import annotations

import asyncio
from collections.abc import Collection
from datetime import datetime, timezone

from app.core.config import get_settings
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job
from app.repositories.job import JobRepository
from app.schemas.structured_jd import (
    BatchStructuredJD,
    BatchStructuredJDItem,
    build_structured_jd_projection,
    build_structured_jd_storage_payload,
)
from app.services.application.blob.job_blob import JobBlobManager
from app.services.infra.blob_storage import BlobNotFoundError, BlobStorageNotConfiguredError
from app.services.infra.text import html_to_text

from .llm_extraction import extract_structured_jd


class JDServiceError(Exception):
    """Base exception for JD service workflows."""


class JobStructuredJDMappingError(JDServiceError):
    """Raised when parsed structured JD items cannot map to input jobs."""

    def __init__(self, job_id: str):
        self.job_id = job_id
        super().__init__(f"Parsed result missing job_id={job_id}")


class JDService:
    """Application service for JD parsing orchestration and persistence."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        *,
        repository: JobRepository | None = None,
        blob_manager: JobBlobManager | None = None,
    ):
        if repository is None:
            if session is None:
                raise ValueError("session or repository is required")
            repository = JobRepository(session)
        self.repository = repository
        self.blob_manager = blob_manager or JobBlobManager()

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

    async def fetch_pending_jobs(
        self,
        limit: int = 5,
        *,
        version_only: bool = False,
        exclude_job_ids: Collection[str] | None = None,
    ) -> list[Job]:
        """Fetch jobs that have content but no up-to-date structured JD yet."""
        return await self.list_pending_jobs_for_parse(
            limit=limit,
            version_only=version_only,
            exclude_job_ids=exclude_job_ids,
        )

    async def parse_jobs(
        self,
        jobs: list[Job],
        persist: bool = False,
    ) -> BatchStructuredJD:
        """Parse a list of jobs and optionally persist structured JD back to DB."""
        if not jobs:
            return BatchStructuredJD(jobs=[])

        jobs_data: list[dict[str, str]] = []
        for job in jobs:
            description = (job.description_plain or "").strip()
            if not description and job.description_html_key:
                try:
                    html_description = await self.blob_manager.load_description_html(job)
                except (BlobNotFoundError, BlobStorageNotConfiguredError):
                    html_description = None
                if html_description:
                    description = html_to_text(html_description)
            jobs_data.append(
                {
                    "job_id": str(job.id),
                    "title": job.title,
                    "description": description,
                }
            )

        settings = get_settings()
        batch_size = max(1, int(getattr(settings, "jd_parse_batch_size", 80)))
        concurrency = max(1, int(getattr(settings, "jd_parse_concurrency", 1)))

        if len(jobs_data) <= batch_size:
            parsed = await extract_structured_jd(jobs_data, is_html=False)
        else:
            chunks = [
                jobs_data[start : start + batch_size]
                for start in range(0, len(jobs_data), batch_size)
            ]

            async def _parse_chunk(
                chunk_index: int,
                chunk_jobs: list[dict[str, str]],
                *,
                semaphore: asyncio.Semaphore | None,
            ) -> tuple[int, BatchStructuredJD]:
                if semaphore is None:
                    parsed_chunk = await extract_structured_jd(chunk_jobs, is_html=False)
                else:
                    async with semaphore:
                        parsed_chunk = await extract_structured_jd(chunk_jobs, is_html=False)
                return chunk_index, parsed_chunk

            semaphore = asyncio.Semaphore(concurrency) if concurrency > 1 else None
            chunk_results = await asyncio.gather(
                *(
                    _parse_chunk(idx, chunk_jobs, semaphore=semaphore)
                    for idx, chunk_jobs in enumerate(chunks)
                )
            )
            chunk_results.sort(key=lambda item: item[0])

            merged_items: list[BatchStructuredJDItem] = []
            for _, chunk in chunk_results:
                merged_items.extend(chunk.jobs)
            parsed = BatchStructuredJD(jobs=merged_items)

        if persist:
            try:
                await self.persist_jobs(jobs, parsed.jobs)
            except Exception as exc:  # pragma: no cover - passthrough wrapper
                raise JDServiceError(str(exc)) from exc

        return parsed

    async def persist_jobs(
        self,
        jobs: list[Job],
        parsed_items: list[BatchStructuredJDItem],
    ) -> None:
        """Persist parsed structured JD items for a batch of jobs."""
        await self.persist_structured_jd_batch(jobs=jobs, parsed_items=parsed_items)

    async def persist_jobs_by_ids(
        self,
        job_ids: list[str],
        parsed_items: list[BatchStructuredJDItem],
    ) -> None:
        """Load jobs by ID and persist a parsed batch."""
        jobs = await self.repository.list_by_ids(job_ids)
        if len(jobs) != len(job_ids):
            missing_job_ids = sorted(set(job_ids) - {str(job.id) for job in jobs})
            raise JDServiceError(f"Missing jobs for persistence: {missing_job_ids}")
        await self.persist_jobs(jobs, parsed_items)

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


__all__ = ["JDService", "JDServiceError", "JobStructuredJDMappingError"]
