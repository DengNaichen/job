"""Job repository for database operations."""

from collections.abc import Collection
from datetime import datetime

from sqlalchemy import update
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, JobStatus


class JobRepository:
    """Repository for Job entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, job: Job) -> Job:
        """Create a new job."""
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def get_by_id(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        return await self.session.get(Job, job_id)

    async def list_by_ids(self, job_ids: list[str]) -> list[Job]:
        """Get jobs by IDs while preserving input order."""
        if not job_ids:
            return []
        result = await self.session.execute(select(Job).where(Job.id.in_(job_ids)))
        jobs = list(result.scalars().all())
        jobs_by_id = {str(job.id): job for job in jobs}
        return [jobs_by_id[job_id] for job_id in job_ids if job_id in jobs_by_id]

    # ------------------------------------------------------------------ #
    # Authoritative source_id-based helpers (Phase 3 cutover)              #
    # ------------------------------------------------------------------ #

    async def list_by_source_id_and_external_ids(
        self,
        source_id: str,
        external_job_ids: list[str],
    ) -> list[Job]:
        """Authoritative: get jobs for one same-source snapshot keyed by source_id."""
        if not external_job_ids:
            return []
        result = await self.session.exec(
            select(Job).where(
                Job.source_id == source_id,
                Job.external_job_id.in_(external_job_ids),
            )
        )
        return list(result.all())

    async def bulk_close_missing_for_source_id(
        self,
        *,
        source_id: str,
        seen_at_before: datetime,
        updated_at: datetime,
    ) -> int:
        """Authoritative: close stale open jobs for a source_id not seen in this snapshot."""
        result = await self.session.exec(
            update(Job)
            .where(
                Job.source_id == source_id,
                Job.status == JobStatus.open,
                Job.last_seen_at < seen_at_before,
            )
            .values(
                status=JobStatus.closed,
                updated_at=updated_at,
            )
        )
        return int(result.rowcount or 0)

    async def source_id_reference_exists(self, source_id: str) -> bool:
        """Return True if any job row references the given source_id."""
        result = await self.session.exec(select(Job.id).where(Job.source_id == source_id).limit(1))
        return result.first() is not None

    # ------------------------------------------------------------------ #
    # Legacy string-based helpers                                          #
    # LEGACY-FALLBACK: remove after enforcement revision (Phase 6).        #
    # ------------------------------------------------------------------ #

    async def list_by_source_and_external_ids(
        self,
        source: str,
        external_job_ids: list[str],
    ) -> list[Job]:
        """Get jobs for one same-source snapshot keyed by external_job_id."""
        if not external_job_ids:
            return []

        result = await self.session.exec(
            select(Job).where(
                Job.source == source,
                Job.external_job_id.in_(external_job_ids),
            )
        )
        return list(result.all())

    async def has_any_for_source(self, *, source: str) -> bool:
        """LEGACY-FALLBACK: return True if any job row uses the given legacy source key."""
        result = await self.session.exec(select(Job.id).where(Job.source == source).limit(1))
        return result.first() is not None

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        status: JobStatus | None = None,
    ) -> list[Job]:
        """List jobs with optional pagination and status filter."""
        statement = select(Job).offset(skip).limit(limit)
        if status is not None:
            statement = statement.where(Job.status == status)
        result = await self.session.exec(statement)
        return list(result.all())

    async def update(self, job: Job) -> Job:
        """Update an existing job."""
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job

    async def save_all(self, jobs: list[Job]) -> None:
        """Save a batch of existing jobs in one commit."""
        for job in jobs:
            self.session.add(job)
        await self.session.commit()

    async def save_all_no_commit(self, jobs: list[Job]) -> None:
        """Stage a batch of jobs in the current transaction without committing."""
        for job in jobs:
            self.session.add(job)

    async def flush(self) -> None:
        """Flush the current unit of work without committing."""
        await self.session.flush()

    async def bulk_close_missing_for_source(
        self,
        *,
        source: str,
        seen_at_before: datetime,
        updated_at: datetime,
    ) -> int:
        """LEGACY-FALLBACK: close stale open jobs for a source string not seen in this snapshot."""
        result = await self.session.exec(
            update(Job)
            .where(
                Job.source == source,
                Job.status == JobStatus.open,
                Job.last_seen_at < seen_at_before,
            )
            .values(
                status=JobStatus.closed,
                updated_at=updated_at,
            )
        )
        return int(result.rowcount or 0)

    async def delete(self, job: Job) -> None:
        """Delete a job."""
        await self.session.delete(job)
        await self.session.commit()

    async def list_pending_structured_jd(
        self,
        limit: int = 5,
        *,
        version_only: bool = False,
        exclude_job_ids: Collection[str] | None = None,
    ) -> list[Job]:
        """List jobs eligible for structured_jd extraction."""
        statement = select(Job).where(
            (Job.description_html.is_not(None)) | (Job.description_plain.is_not(None))
        )
        if version_only:
            statement = statement.where(Job.structured_jd.is_not(None)).where(
                Job.structured_jd_version < 3
            )
        else:
            statement = statement.where(
                (Job.structured_jd.is_(None)) | (Job.structured_jd_version < 3)
            )
        if exclude_job_ids:
            statement = statement.where(Job.id.not_in(list(exclude_job_ids)))
        statement = statement.order_by(Job.updated_at, Job.id).limit(limit)
        result = await self.session.execute(statement)
        return list(result.scalars().all())
