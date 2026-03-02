from sqlalchemy import delete
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.job_location import JobLocation


class JobLocationRepository:
    """Repository for JobLocation link entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_by_job_id(self, job_id: str) -> list[JobLocation]:
        """List all location links for a given job."""
        statement = select(JobLocation).where(JobLocation.job_id == job_id)
        result = await self.session.exec(statement)
        return list(result.all())

    async def link(
        self,
        job_id: str,
        location_id: str,
        is_primary: bool = False,
        source_raw: str | None = None,
    ) -> JobLocation:
        """Link a job to a location. Idempotent."""
        statement = select(JobLocation).where(
            JobLocation.job_id == job_id, JobLocation.location_id == location_id
        )
        result = await self.session.exec(statement)
        existing = result.first()

        if existing:
            if existing.is_primary != is_primary or existing.source_raw != source_raw:
                existing.is_primary = is_primary
                existing.source_raw = source_raw
                self.session.add(existing)
            return existing

        job_loc = JobLocation(
            job_id=job_id,
            location_id=location_id,
            is_primary=is_primary,
            source_raw=source_raw,
        )
        self.session.add(job_loc)
        return job_loc

    async def unlink(self, job_id: str, location_id: str) -> None:
        """Remove a link between a job and a location."""
        statement = delete(JobLocation).where(
            (JobLocation.job_id == job_id) & (JobLocation.location_id == location_id)
        )
        await self.session.exec(statement)

    async def set_primary(self, job_id: str, location_id: str) -> None:
        """Set a specific location as primary for a job, unsetting others."""
        # Unset existing primary entries for this job
        links = await self.list_by_job_id(job_id)
        for link in links:
            if link.is_primary and link.location_id != location_id:
                link.is_primary = False
                self.session.add(link)
            elif link.location_id == location_id and not link.is_primary:
                link.is_primary = True
                self.session.add(link)
