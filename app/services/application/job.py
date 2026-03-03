"""Job service for business logic."""

from datetime import datetime, timezone

from app.models import Job, JobStatus
from app.repositories.job import JobRepository
from app.repositories.source import SourceRepository
from app.schemas.job import JobCreate, JobUpdate
from app.services.application.job_blob import JobBlobManager, JobBlobPointers
from app.services.infra.text import html_to_text


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


class SourceResolutionError(JobError):
    """Raised when a legacy source string cannot be resolved to a known source."""

    def __init__(self, source_key: str):
        super().__init__(
            code="SOURCE_NOT_FOUND",
            message=f"Cannot resolve '{source_key}' to a known source",
        )
        self.source_key = source_key


class JobService:
    """Service for Job business logic."""

    _LEGACY_STRUCTURED_LOCATION_FIELDS = {
        "source",
        "location_text",
        "location_city",
        "location_region",
        "location_country_code",
        "location_workplace_type",
        "location_remote_scope",
    }

    def __init__(
        self,
        repository: JobRepository,
        blob_manager: JobBlobManager | None = None,
        source_repository: SourceRepository | None = None,
    ):
        self.repository = repository
        self.blob_manager = blob_manager or JobBlobManager()
        self.source_repository = source_repository

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
        """Create a new job, resolving source_id from the legacy source string when needed."""
        job_data = job_in.model_dump()
        description_html = job_data.pop("description_html", None)
        raw_payload = job_data.pop("raw_payload", {})
        if (
            not job_data.get("description_plain")
            and isinstance(description_html, str)
            and description_html.strip()
        ):
            job_data["description_plain"] = html_to_text(description_html)
        legacy_source_key = job_data.get("source")
        job_data.pop("location_hints", None)
        for field in self._LEGACY_STRUCTURED_LOCATION_FIELDS:
            job_data.pop(field, None)

        # Resolve source_id from legacy source string when not already supplied.
        if not job_data.get("source_id"):
            source_key = legacy_source_key if isinstance(legacy_source_key, str) else None
            if source_key and self.source_repository:
                source = await self.source_repository.get_by_source_key(source_key)
                if source is None:
                    raise SourceResolutionError(source_key)
                job_data["source_id"] = source.id
            else:
                raise SourceResolutionError(source_key or "<missing-source-key>")

        job = Job(**job_data)
        await self.blob_manager.sync_job_blobs(
            job,
            description_html=description_html,
            raw_payload=raw_payload,
        )
        return await self.repository.create(job)

    async def update_job(self, job_id: str, job_in: JobUpdate) -> Job:
        """Partially update a job."""
        job = await self.repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError()

        existing_pointers = JobBlobPointers.from_job(job)
        update_data = job_in.model_dump(exclude_unset=True)
        explicit_fields = set(update_data)
        description_html = update_data.pop("description_html", None)
        raw_payload = update_data.pop("raw_payload", None)
        if (
            "description_html" in explicit_fields
            and "description_plain" not in update_data
            and isinstance(description_html, str)
            and description_html.strip()
        ):
            update_data["description_plain"] = html_to_text(description_html)
        update_data.pop("location_hints", None)
        for field in self._LEGACY_STRUCTURED_LOCATION_FIELDS:
            update_data.pop(field, None)
        for key, value in update_data.items():
            setattr(job, key, value)
        job.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        blob_kwargs: dict[str, object] = {}
        if "description_html" in explicit_fields:
            blob_kwargs["description_html"] = description_html
        if "raw_payload" in explicit_fields:
            blob_kwargs["raw_payload"] = raw_payload
        await self.blob_manager.sync_job_blobs(
            job,
            existing_pointers=existing_pointers,
            explicit_fields=explicit_fields,
            **blob_kwargs,
        )

        return await self.repository.update(job)

    async def delete_job(self, job_id: str) -> None:
        """Delete a job by ID."""
        job = await self.repository.get_by_id(job_id)
        if not job:
            raise JobNotFoundError()
        await self.repository.delete(job)
