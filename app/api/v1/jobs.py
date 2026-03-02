"""Job API endpoints with source_id compatibility support."""

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models import Job, JobStatus
from app.repositories.job import JobRepository
from app.repositories.source import SourceRepository
from app.schemas.job import JobCreate, JobRead, JobUpdate
from app.services.application.job import JobNotFoundError, JobService, SourceResolutionError

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_service(session: AsyncSession = Depends(get_session)) -> JobService:
    """Dependency injection for JobService with source resolution support."""
    repository = JobRepository(session)
    source_repository = SourceRepository(session)
    return JobService(repository, source_repository=source_repository)


@router.get("/", response_model=list[JobRead])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status: JobStatus | None = None,
    service: JobService = Depends(get_job_service),
) -> list[Job]:
    return await service.list_jobs(skip=skip, limit=limit, status=status)


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return await service.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@router.post("/", response_model=JobRead, status_code=201)
async def create_job(
    job_in: JobCreate,
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return await service.create_job(job_in)
    except SourceResolutionError as e:
        raise HTTPException(status_code=422, detail=e.message)


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: str,
    job_in: JobUpdate,
    service: JobService = Depends(get_job_service),
) -> Job:
    try:
        return await service.update_job(job_id, job_in)
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
