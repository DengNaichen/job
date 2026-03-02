import pytest

from bs4 import BeautifulSoup

from app.models.job import Job, WorkplaceType
from sqlmodel.ext.asyncio.session import AsyncSession
from scripts.backfill_job_locations_v3 import apply_backfill_to_job_v3


class TestBackfillJobLocationsV3:
    @pytest.mark.asyncio
    async def test_apply_backfill_high_confidence(self, session: AsyncSession):
        """High confidence raw payload should populate fields where they are missing."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(
            Job(
                source="smartrecruiters",
                raw_payload={
                    "name": "Test Job",
                    "applyUrl": "http://test",
                    "location": {"city": "Paris", "region": "IDF", "country": "FR", "remote": True},
                },
                location_text="France",
                title="Test Job",
                external_job_id="sr-123",
                apply_url="http://test"
            )
        )

        assert await apply_backfill_to_job_v3(session, job) is True
        
        # Verify sync back to job fields
        assert job.location_city == "Paris"
        assert job.location_region == "IDF"
        assert job.location_country_code == "FR"
        assert job.location_workplace_type == WorkplaceType.remote
        
        # Verify links
        from app.repositories.job_location import JobLocationRepository
        links = await JobLocationRepository(session).list_by_job_id(job.id)
        assert len(links) == 1
        assert links[0].is_primary is True

    @pytest.mark.asyncio
    async def test_apply_backfill_low_confidence_fallback(self, session: AsyncSession):
        """Should fallback to text parsing if raw_payload doesn't yield structure."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(
            Job(
                source="ashby",
                title="Test",
                external_job_id="ashby-1",
                apply_url="http://test",
                raw_payload={"title": "Test", "applyUrl": "http://test"},
                location_text="San Francisco, CA",
            )
        )

        assert await apply_backfill_to_job_v3(session, job) is True
        assert job.location_city == "San Francisco"
        assert job.location_region == "CA"
        assert job.location_country_code == "US"

    @pytest.mark.asyncio
    async def test_apply_backfill_idempotent_reruns(self, session: AsyncSession):
        """Running twice shouldn't change already backfilled data if it yielded same result."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(Job(
            source="smartrecruiters",
            title="Test",
            external_job_id="sr-456",
            apply_url="http://test",
            raw_payload={
                "name": "Test Job",
                "applyUrl": "http://test",
                "location": {"city": "Paris", "region": "IDF", "country": "FR"},
            },
        ))

        assert await apply_backfill_to_job_v3(session, job) is True
        assert job.location_city == "Paris"

        # Second run should return False (no external field change, no link added)
        assert await apply_backfill_to_job_v3(session, job) is False

    @pytest.mark.asyncio
    async def test_protection_against_low_confidence_overwrites(self, session: AsyncSession):
        """If existing data is present, low-confidence text parse shouldn't overwrite it."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(Job(
            source="ashby",
            title="Test",
            external_job_id="ashby-2",
            apply_url="http://test",
            location_city="Existing City",
            location_region="EX",
            location_country_code="US",
            location_text="San Francisco, CA",
            raw_payload={
                "title": "Test",
                "applyUrl": "http://test",
            },
        ))

        # We fallback to text parser, it parses San Francisco.
        # But wait, in v3, we ensure we don't overwrite if existing strong data is present.
        
        # Test apply: it should capture "Existing City" and create its canonical form.
        assert await apply_backfill_to_job_v3(session, job) is True
        
        # Original city shouldn't be overwritten with San Francisco
        assert job.location_city == "Existing City"
        assert job.location_region == "EX"
        assert job.location_country_code == "US"

    @pytest.mark.asyncio
    async def test_high_confidence_overwrites(self, session: AsyncSession):
        """High confidence sources CAN overwrite if they parse better data."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(Job(
            source="smartrecruiters",
            title="Test",
            external_job_id="sr-999",
            apply_url="http://test",
            location_city="Old City",
            location_text="Paris",
            raw_payload={
                "name": "Test Job",
                "applyUrl": "http://test",
                "location": {"city": "Paris", "region": "IDF", "country": "FR"},
            },
        ))

        assert await apply_backfill_to_job_v3(session, job) is True
        assert job.location_city == "Paris"
        assert job.location_region == "IDF"
        assert job.location_country_code == "FR"

    @pytest.mark.asyncio
    async def test_update_missing_country_with_text(self, session: AsyncSession):
        """Should patch missing canonical country using text parsing without touching existing city."""
        from app.repositories.job import JobRepository
        repo = JobRepository(session)
        job = await repo.create(Job(
            source="ashby",
            title="Test",
            external_job_id="ashby-3",
            apply_url="http://test",
            location_city="Existing City",
            location_country_code=None,
            location_text="Existing City, Canada",
            raw_payload={},
        ))

        assert await apply_backfill_to_job_v3(session, job) is True
        assert job.location_city == "Existing City"
        assert job.location_country_code == "CA"

