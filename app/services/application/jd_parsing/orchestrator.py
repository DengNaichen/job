"""Batch JD parsing orchestrator."""

from collections.abc import Collection

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.structured_jd import BatchStructuredJD
from app.schemas.structured_jd import BatchStructuredJDItem
from app.services.application.blob.job_blob import JobBlobManager
from app.services.application.jd_parsing.structured_jd import StructuredJDService
from app.services.infra.blob_storage import BlobNotFoundError, BlobStorageNotConfiguredError
from app.services.infra.text import html_to_text

from .llm_extraction import extract_structured_jd


class JDParseServiceError(Exception):
    """Base exception for JD parsing service errors."""


class JDBatchParseService:
    """Batch JD parsing service for pending jobs."""

    def __init__(self, session: AsyncSession):
        self.structured_jd_service = StructuredJDService(JobRepository(session))
        self.blob_manager = JobBlobManager()

    async def fetch_pending_jobs(
        self,
        limit: int = 5,
        *,
        version_only: bool = False,
        exclude_job_ids: Collection[str] | None = None,
    ) -> list[Job]:
        """Fetch jobs that have HTML description but no structured JD yet."""
        return await self.structured_jd_service.list_pending_jobs_for_parse(
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

        parsed = await extract_structured_jd(jobs_data, is_html=False)

        if persist:
            try:
                await self.persist_jobs(jobs, parsed.jobs)
            except Exception as exc:  # pragma: no cover - passthrough wrapper
                raise JDParseServiceError(str(exc)) from exc

        return parsed

    async def persist_jobs(self, jobs: list[Job], parsed_items: list) -> None:
        """Persist parsed structured JD items for a batch of jobs."""
        await self.structured_jd_service.persist_structured_jd_batch(
            jobs=jobs,
            parsed_items=parsed_items,
        )

    async def persist_jobs_by_ids(
        self,
        job_ids: list[str],
        parsed_items: list[BatchStructuredJDItem],
    ) -> None:
        """Load jobs by ID and persist a parsed batch."""
        jobs = await self.structured_jd_service.repository.list_by_ids(job_ids)
        if len(jobs) != len(job_ids):
            missing_job_ids = sorted(set(job_ids) - {str(job.id) for job in jobs})
            raise JDParseServiceError(f"Missing jobs for persistence: {missing_job_ids}")
        await self.persist_jobs(jobs, parsed_items)
