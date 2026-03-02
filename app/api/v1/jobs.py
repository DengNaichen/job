"""Job API endpoints with source_id compatibility support."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from sqlalchemy.orm.attributes import instance_state

from app.core.database import get_session
from app.models import Job, JobStatus, build_source_key
from app.repositories.job import JobRepository
from app.schemas.location import JobLocationRead
from app.repositories.source import SourceRepository
from app.schemas.job import JobCreate, JobRead, JobUpdate
from app.services.application.job import JobNotFoundError, JobService, SourceResolutionError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(session: AsyncSession = Depends(get_session)) -> JobService:
    """Dependency injection for JobService with source resolution support."""
    repository = JobRepository(session)
    source_repository = SourceRepository(session)
    return JobService(repository, source_repository=source_repository)


def _map_job_to_read(job: Job) -> JobRead:
    """Helper to map a Job model to JobRead, injecting explicitly loaded locations."""
    data = job.model_dump()
    state = instance_state(job)
    source_record = state.dict.get("source_record")
    if source_record is not None:
        data["source"] = build_source_key(source_record.platform, source_record.identifier)
    else:
        data["source"] = None

    if "job_locations" in state.dict:
        links = state.dict["job_locations"]
        data["locations"] = [JobLocationRead.model_validate(link).model_dump() for link in links]
        primary = next((link for link in links if link.is_primary), None)
        data["location_text"] = (
            primary.source_raw.strip()
            if primary and isinstance(primary.source_raw, str) and primary.source_raw.strip()
            else None
        )
    else:
        data["locations"] = []
        data["location_text"] = None
    return JobRead.model_validate(data)


@router.get("/", response_model=list[JobRead])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status: JobStatus | None = None,
    service: JobService = Depends(get_job_service),
) -> list[JobRead]:
    jobs = await service.list_jobs(skip=skip, limit=limit, status=status)
    return [_map_job_to_read(job) for job in jobs]


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    try:
        job = await service.get_job(job_id)
        return _map_job_to_read(job)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.post("/", response_model=JobRead, status_code=201)
async def create_job(
    job_in: JobCreate,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    try:
        job = await service.create_job(job_in)
        return _map_job_to_read(job)
    except SourceResolutionError as e:
        raise HTTPException(status_code=422, detail=e.message)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: str,
    job_in: JobUpdate,
    service: JobService = Depends(get_job_service),
) -> JobRead:
    try:
        job = await service.update_job(job_id, job_in)
        return _map_job_to_read(job)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> None:
    try:
        await service.delete_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")
