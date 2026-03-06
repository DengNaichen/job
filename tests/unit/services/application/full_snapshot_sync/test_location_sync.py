import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.job import Job, WorkplaceType
from app.models.job_location import JobLocation
from app.services.application.full_snapshot_sync.location_sync import sync_job_location
from app.services.domain.location import StructuredLocation


@pytest.mark.asyncio
async def test_sync_job_location_idempotency(session: AsyncSession) -> None:
    job = Job(
        source="lever",
        external_job_id="test-123",
        title="Software Engineer",
        apply_url="https://example.com",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    structured = StructuredLocation(
        city="San Francisco",
        region="CA",
        country_code="US",
        workplace_type=WorkplaceType.onsite,
    )

    loc1 = await sync_job_location(
        session=session,
        job_id=job.id,
        structured=structured,
        is_primary=True,
        source_raw="San Francisco, CA",
    )

    assert loc1.canonical_key == "us-ca-san-francisco"

    loc2 = await sync_job_location(
        session=session,
        job_id=job.id,
        structured=structured,
        is_primary=True,
        source_raw="San Francisco, CA",
    )

    assert loc1.id == loc2.id
    links = (
        await session.exec(
            select(JobLocation).where(JobLocation.job_id == job.id, JobLocation.location_id == loc1.id)
        )
    ).all()
    assert len(links) == 1
    assert links[0].workplace_type == "onsite"
