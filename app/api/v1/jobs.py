from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.models import Job, JobStatus
from app.schemas.job import JobCreate, JobRead, JobUpdate

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/", response_model=list[JobRead])
async def list_jobs(
    skip: int = 0,
    limit: int = 100,
    status: JobStatus | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[Job]:
    statement = select(Job).offset(skip).limit(limit)
    if status:
        statement = statement.where(Job.status == status)
    result = await session.exec(statement)
    return list(result.all())


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/", response_model=JobRead, status_code=201)
async def create_job(
    job_in: JobCreate,
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = Job(**job_in.model_dump())
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@router.patch("/{job_id}", response_model=JobRead)
async def update_job(
    job_id: str,
    job_in: JobUpdate,
    session: AsyncSession = Depends(get_session),
) -> Job:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job_data = job_in.model_dump(exclude_unset=True)
    for key, value in job_data.items():
        setattr(job, key, value)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
) -> None:
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    await session.delete(job)
    await session.commit()
