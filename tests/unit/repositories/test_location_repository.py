import pytest

from sqlmodel.ext.asyncio.session import AsyncSession
from sqlalchemy.exc import IntegrityError


class TestLocationRepository:
    """Tests for LocationRepository (T015)."""

    @pytest.mark.asyncio
    async def test_upsert_idempotency(self, session: AsyncSession):
        """Test that upserting the same canonical key doesn't throw or duplicate locations."""
        from app.models.location import Location
        from app.repositories.location import LocationRepository

        repo = LocationRepository(session)
        loc1 = Location(
            canonical_key="US#CA#SF",
            display_name="San Francisco, CA, US",
            city="San Francisco",
            region="CA",
            country_code="US",
        )
        
        # First upsert
        created1 = await repo.upsert(loc1)
        assert created1.id is not None
        assert created1.canonical_key == "US#CA#SF"

        # Second upsert with same canonical key
        loc2 = Location(
            canonical_key="US#CA#SF",
            display_name="San Francisco, CA, US (Updated)",
            city="San Francisco",
            region="CA",
            country_code="US",
        )
        created2 = await repo.upsert(loc2)
        
        # Should return same ID
        assert created1.id == created2.id
        
        # Depending on upsert logic, it might have updated display_name or kept the old one.
        # But critically, no duplicate row was created.
        
        # Verify db representation has exactly 1 entry for this key
        found = await repo.get_by_canonical_key("US#CA#SF")
        assert found is not None
        assert found.id == created1.id

    @pytest.mark.asyncio
    async def test_get_by_canonical_key(self, session: AsyncSession):
        """Test retrieving location by canonical key."""
        from app.models.location import Location
        from app.repositories.location import LocationRepository

        repo = LocationRepository(session)
        loc = Location(
            canonical_key="UK#ENG#LON",
            display_name="London, UK",
        )
        await repo.upsert(loc)

        found = await repo.get_by_canonical_key("UK#ENG#LON")
        assert found is not None
        assert found.display_name == "London, UK"

    @pytest.mark.asyncio
    async def test_get_by_id(self, session: AsyncSession):
        """Test retrieving location by internal ID."""
        from app.models.location import Location
        from app.repositories.location import LocationRepository

        repo = LocationRepository(session)
        loc = await repo.upsert(Location(canonical_key="FR##PAR", display_name="Paris, FR"))

        found = await repo.get_by_id(loc.id)
        assert found is not None
        assert found.canonical_key == "FR##PAR"
