"""Job service for business logic."""

from collections.abc import Collection
from datetime import datetime, timezone

from app.models import Job, JobStatus
from app.repositories.job import JobRepository
from app.schemas.job import JobCreate, JobUpdate
from app.schemas.structured_jd import (
    BatchStructuredJDItem,
    build_structured_jd_projection,
    build_structured_jd_storage_payload,
)
from app.services.blob_storage import JobBlobManager, JobBlobPointers


class JobError(Exception):
    """Base exception for Job service errors."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class JobNotFoundError(JobError):
    """Raised when a job is not found."""

    def __init__(self):
        super().__init__(code="NOT_FOUND", message="Job not found")


class JobStructuredJDMappingError(JobError):
    """Raised when parsed structured JD items cannot map to input jobs."""

    def __init__(self, job_id: str):
        super().__init__(
            code="STRUCTURED_JD_MAPPING_ERROR",
            message=f"Parsed result missing job_id={job_id}",
        )
        self.job_id = job_id


class JobService:
    """Service for Job business logic."""

    def __init__(
        self,
        repository: JobRepository,
        blob_manager: JobBlobManager | None = None,
    ):
        self.repository = repository
        self.blob_manager = blob_manager or JobBlobManager()

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        status: JobStatus | None = None,
    ) -> list[Job]:
        """List jobs with optional status filtering."""
        return await self.repository.list_jobs(skip=skip, limit=limit, status=status)

    async def get_job(self, job_id: str) -> Job:
        """Get a job by ID."""
        job = await self.repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError()
        return job

    async def list_jobs_by_ids(self, job_ids: list[str]) -> list[Job]:
        """Get jobs by ID while preserving input order."""
        return await self.repository.list_by_ids(job_ids)

    async def create_job(self, job_in: JobCreate) -> Job:
        """Create a new job."""
        job = Job(**job_in.model_dump())
        await self.blob_manager.sync_job_blobs(job)
        return await self.repository.create(job)

    async def update_job(self, job_id: str, job_in: JobUpdate) -> Job:
        """Partially update a job."""
        job = await self.repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError()

        existing_pointers = JobBlobPointers.from_job(job)
        update_data = job_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        await self.blob_manager.sync_job_blobs(
            job,
            existing_pointers=existing_pointers,
            explicit_fields=set(update_data),
        )

        return await self.repository.update(job)

    async def delete_job(self, job_id: str) -> None:
        """Delete a job by ID."""
        job = await self.repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError()
        await self.repository.delete(job)

    async def list_pending_jobs_for_jd_parse(
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
