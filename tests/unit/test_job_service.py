"""Unit tests for JobService."""

from unittest.mock import AsyncMock

import pytest

from app.models import Job
from app.schemas.job import JobCreate, JobUpdate
from app.schemas.structured_jd import BatchStructuredJDItem
from app.services.application.job import (
    JobNotFoundError,
    JobService,
)
from app.services.application.structured_jd import (
    JobStructuredJDMappingError,
    StructuredJDService,
)


def _build_job(job_id: str = "job-1") -> Job:
    """Build a minimal Job model for service tests."""
    return Job(
        id=job_id,
        source="greenhouse",
        external_job_id=f"ext-{job_id}",
        title="Backend Engineer",
        apply_url="https://example.com/apply",
        raw_payload={},
    )


@pytest.mark.asyncio
async def test_get_job_not_found() -> None:
    """get_job should raise JobNotFoundError when repository returns None."""
    repository = AsyncMock()
    repository.get_by_id.return_value = None
    service = JobService(repository=repository)

    with pytest.raises(JobNotFoundError):
        await service.get_job("missing-job")


@pytest.mark.asyncio
async def test_create_job() -> None:
    """create_job should map JobCreate into model and call repository.create."""
    repository = AsyncMock()
    created = _build_job()
    repository.create.return_value = created
    service = JobService(repository=repository)

    payload = JobCreate(
        source="greenhouse",
        external_job_id="123",
        title="Engineer",
        apply_url="https://example.com",
    )
    result = await service.create_job(payload)

    assert result == created
    repository.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_job_updates_timestamp() -> None:
    """update_job should apply fields and refresh updated_at."""
    repository = AsyncMock()
    job = _build_job()
    previous_updated_at = job.updated_at
    repository.get_by_id.return_value = job
    repository.update.return_value = job
    service = JobService(repository=repository)

    updated = await service.update_job("job-1", JobUpdate(title="Senior Engineer"))

    previous_updated_at_naive = (
        previous_updated_at.replace(tzinfo=None)
        if previous_updated_at.tzinfo
        else previous_updated_at
    )
    assert updated.title == "Senior Engineer"
    assert updated.updated_at >= previous_updated_at_naive
    repository.update.assert_awaited_once_with(job)


@pytest.mark.asyncio
async def test_persist_structured_jd_batch() -> None:
    """persist_structured_jd_batch should map parsed items and save once."""
    repository = AsyncMock()
    service = StructuredJDService(repository=repository)
    jobs = [_build_job("job-1"), _build_job("job-2")]

    parsed_items = [
        BatchStructuredJDItem(
            job_id="job-1",
            required_skills=["Python"],
            keywords=["backend"],
            experience_years=3,
            sponsorship_not_available="yes",
            job_domain_raw="Treasury Operations",
            job_domain_normalized="finance_treasury",
            min_degree_level="bachelor",
        ),
        BatchStructuredJDItem(
            job_id="job-2",
            required_skills=["Go"],
            keywords=["distributed systems"],
            experience_years=5,
            sponsorship_not_available="unknown",
            job_domain_raw="Platform Engineering",
            job_domain_normalized="software_engineering",
            min_degree_level="master",
        ),
    ]

    await service.persist_structured_jd_batch(jobs=jobs, parsed_items=parsed_items)

    assert jobs[0].structured_jd is not None
    assert jobs[0].structured_jd["required_skills"] == ["Python"]
    assert jobs[1].structured_jd is not None
    assert jobs[1].structured_jd["required_skills"] == ["Go"]
    assert "sponsorship_not_available" not in jobs[0].structured_jd
    assert "job_domain_normalized" not in jobs[0].structured_jd
    assert "min_degree_level" not in jobs[0].structured_jd
    assert jobs[0].structured_jd_updated_at is not None
    assert jobs[1].structured_jd_updated_at is not None
    assert jobs[0].sponsorship_not_available == "yes"
    assert jobs[0].job_domain_normalized == "finance_treasury"
    assert jobs[0].min_degree_level == "bachelor"
    assert jobs[0].min_degree_rank == 2
    assert jobs[0].structured_jd_version == 3
    assert jobs[1].job_domain_normalized == "software_engineering"
    assert jobs[1].min_degree_rank == 3
    repository.save_all.assert_awaited_once_with(jobs)


@pytest.mark.asyncio
async def test_persist_structured_jd_batch_missing_mapping() -> None:
    """persist_structured_jd_batch should fail when an input job is missing."""
    repository = AsyncMock()
    service = StructuredJDService(repository=repository)
    jobs = [_build_job("job-1")]
    parsed_items = [
        BatchStructuredJDItem(
            job_id="job-2",
            required_skills=["Python"],
        )
    ]

    with pytest.raises(JobStructuredJDMappingError):
        await service.persist_structured_jd_batch(jobs=jobs, parsed_items=parsed_items)

    repository.save_all.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_pending_jobs_for_parse_passes_filters() -> None:
    """list_pending_jobs_for_parse should forward version and exclusion filters."""
    repository = AsyncMock()
    jobs = [_build_job("job-1")]
    repository.list_pending_structured_jd.return_value = jobs
    service = StructuredJDService(repository=repository)

    result = await service.list_pending_jobs_for_parse(
        limit=10,
        version_only=True,
        exclude_job_ids={"job-2", "job-3"},
    )

    assert result == jobs
    repository.list_pending_structured_jd.assert_awaited_once_with(
        limit=10,
        version_only=True,
        exclude_job_ids={"job-2", "job-3"},
    )
