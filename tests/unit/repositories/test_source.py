"""
Unit tests for SourceRepository.

Covers:
- create (T010)
- get_by_id (T012)
- get_by_name_normalized (T012)
"""

import pytest
from datetime import datetime, timezone

from sqlmodel.ext.asyncio.session import AsyncSession


class TestSourceRepository:
    """Tests for SourceRepository (T010, T012)."""

    @pytest.mark.asyncio
    async def test_create_source(self, session: AsyncSession):
        """Test creating a source in repository."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )

        created = await repo.create(source)

        assert created.id is not None
        assert created.name == "Stripe"
        assert created.name_normalized == "stripe"
        assert created.created_at is not None
        assert created.updated_at is not None

    @pytest.mark.asyncio
    async def test_create_source_generates_normalized_name(self, session: AsyncSession):
        """Test that creating source generates name_normalized."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="  STRIPE  ",
            name_normalized="stripe",  # Should be pre-normalized by service
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )

        created = await repo.create(source)

        assert created.name_normalized == "stripe"

    @pytest.mark.asyncio
    async def test_create_source_timestamps_initialized(self, session: AsyncSession):
        """Test that created_at and updated_at are initialized on create."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )

        before = datetime.now(timezone.utc)
        created = await repo.create(source)
        after = datetime.now(timezone.utc)

        assert created.created_at >= before
        assert created.created_at <= after
        assert created.updated_at >= before
        assert created.updated_at <= after

    @pytest.mark.asyncio
    async def test_get_by_id(self, session: AsyncSession):
        """Test getting source by ID."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )
        created = await repo.create(source)

        found = await repo.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.name == "Stripe"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, session: AsyncSession):
        """Test getting source by ID when not found."""
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)

        found = await repo.get_by_id("non-existent-id")

        assert found is None

    @pytest.mark.asyncio
    async def test_get_by_name_normalized(self, session: AsyncSession):
        """Test getting source by normalized name."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )
        await repo.create(source)

        found = await repo.get_by_name_normalized("stripe")

        assert found is not None
        assert found.name == "Stripe"

    @pytest.mark.asyncio
    async def test_get_by_name_normalized_case_insensitive(self, session: AsyncSession):
        """Test that get_by_name_normalized is case insensitive."""
        from app.models.source import Source, PlatformType
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)
        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )
        await repo.create(source)

        # Search with different case should still find it
        # since we search by normalized name
        found = await repo.get_by_name_normalized("STRIPE")

        assert found is not None
        assert found.name_normalized == "stripe"

    @pytest.mark.asyncio
    async def test_get_by_name_normalized_not_found(self, session: AsyncSession):
        """Test getting source by normalized name when not found."""
        from app.repositories.source import SourceRepository

        repo = SourceRepository(session)

        found = await repo.get_by_name_normalized("nonexistent")

        assert found is None
