import pytest

from sqlmodel.ext.asyncio.session import AsyncSession


class TestJobLocationRepository:
    """Tests for JobLocationRepository (T015)."""

    @pytest.fixture
    async def setup_models(self, session: AsyncSession):
        from app.models.job import Job
        from app.models.location import Location
        from app.repositories.job import JobRepository
        from app.repositories.location import LocationRepository

        job_repo = JobRepository(session)
        loc_repo = LocationRepository(session)

        job = await job_repo.create(Job(
            source="test",
            external_job_id="test-123",
            title="Tester",
            apply_url="http://test",
        ))
        
        loc1 = await loc_repo.upsert(Location(canonical_key="LOC1", display_name="Location 1"))
        loc2 = await loc_repo.upsert(Location(canonical_key="LOC2", display_name="Location 2"))
        
        return job, loc1, loc2

    @pytest.mark.asyncio
    async def test_link_idempotency(self, session: AsyncSession, setup_models):
        """Test linking job to location is idempotent."""
        from app.repositories.job_location import JobLocationRepository

        job, loc1, _ = setup_models
        repo = JobLocationRepository(session)

        # First link
        link1 = await repo.link(job_id=job.id, location_id=loc1.id, is_primary=True, source_raw="test")
        assert link1 is not None
        assert link1.is_primary is True

        # Second link with same parameters
        link2 = await repo.link(job_id=job.id, location_id=loc1.id, is_primary=False, source_raw="test updated")
        
        # It should update the existing link without duplicating
        links = await repo.list_by_job_id(job.id)
        assert len(links) == 1
        assert links[0].is_primary is False
        assert links[0].source_raw == "test updated"

    @pytest.mark.asyncio
    async def test_unlink(self, session: AsyncSession, setup_models):
        """Test unlinking a location."""
        from app.repositories.job_location import JobLocationRepository

        job, loc1, _ = setup_models
        repo = JobLocationRepository(session)

        await repo.link(job_id=job.id, location_id=loc1.id)
        links_before = await repo.list_by_job_id(job.id)
        assert len(links_before) == 1

        await repo.unlink(job_id=job.id, location_id=loc1.id)
        
        links_after = await repo.list_by_job_id(job.id)
        assert len(links_after) == 0

    @pytest.mark.asyncio
    async def test_set_primary(self, session: AsyncSession, setup_models):
        """Test that set_primary unsets previous primary link."""
        from app.repositories.job_location import JobLocationRepository

        job, loc1, loc2 = setup_models
        repo = JobLocationRepository(session)

        await repo.link(job_id=job.id, location_id=loc1.id, is_primary=True)
        await repo.link(job_id=job.id, location_id=loc2.id, is_primary=False)
        
        # Verify initial state
        links = await repo.list_by_job_id(job.id)
        loc1_link = next(l for l in links if l.location_id == loc1.id)
        loc2_link = next(l for l in links if l.location_id == loc2.id)
        assert loc1_link.is_primary is True
        assert loc2_link.is_primary is False

        # Set loc2 as primary
        await repo.set_primary(job_id=job.id, location_id=loc2.id)
        
        # Check new state
        links_after = await repo.list_by_job_id(job.id)
        loc1_link_after = next(l for l in links_after if l.location_id == loc1.id)
        loc2_link_after = next(l for l in links_after if l.location_id == loc2.id)
        
        assert loc1_link_after.is_primary is False
        assert loc2_link_after.is_primary is True
