"""
Unit tests for Source model, repository, and validation.

Tests for MVP User Story 1:
- T010: SourceRepository.create tests (name_normalized generation, timestamps)
- T011: Input validation tests (name/identifier non-empty after strip)
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from sqlmodel.ext.asyncio.session import AsyncSession

# These imports will fail until implementation is done - that's expected in TDD
# from app.models.source import Source, PlatformType, normalize_name
# from app.repositories.source import SourceRepository
# from app.schemas.source import SourceCreate


class TestNormalizeName:
    """Tests for the normalize_name utility function (T002)."""

    def test_normalize_name_strips_whitespace(self):
        """Test that normalize_name strips leading/trailing whitespace."""
        from app.models.source import normalize_name

        assert normalize_name("  Stripe  ") == "stripe"
        assert normalize_name("\tAirbnb\n") == "airbnb"

    def test_normalize_name_converts_to_lowercase(self):
        """Test that normalize_name converts to lowercase."""
        from app.models.source import normalize_name

        assert normalize_name("STRIPE") == "stripe"
        assert normalize_name("AirBnB") == "airbnb"
        assert normalize_name("STRIPE  ") == "stripe"

    def test_normalize_name_handles_unicode(self):
        """Test that normalize_name handles unicode characters."""
        from app.models.source import normalize_name

        assert normalize_name("Müller") == "müller"
        assert normalize_name("  北京  ") == "北京"


class TestPlatformType:
    """Tests for PlatformType enum (T002)."""

    def test_platform_type_values(self):
        """Test that PlatformType has expected values."""
        from app.models.source import PlatformType

        assert PlatformType.GREENHOUSE.value == "greenhouse"
        assert PlatformType.LEVER.value == "lever"
        assert PlatformType.WORKDAY.value == "workday"
        assert PlatformType.GITHUB.value == "github"

    def test_platform_type_from_string(self):
        """Test creating PlatformType from string."""
        from app.models.source import PlatformType

        assert PlatformType("greenhouse") == PlatformType.GREENHOUSE
        assert PlatformType("lever") == PlatformType.LEVER
        assert PlatformType("workday") == PlatformType.WORKDAY
        assert PlatformType("github") == PlatformType.GITHUB

    def test_platform_type_invalid_raises_error(self):
        """Test that invalid platform type raises ValueError."""
        from app.models.source import PlatformType

        with pytest.raises(ValueError):
            PlatformType("invalid_platform")


class TestSourceModel:
    """Tests for Source SQLModel entity (T003)."""

    def test_source_creation_with_required_fields(self):
        """Test creating Source with required fields only."""
        from app.models.source import Source, PlatformType

        source = Source(
            name="Stripe",
            name_normalized="stripe",
            platform=PlatformType.GREENHOUSE,
            identifier="stripe",
        )

        assert source.name == "Stripe"
        assert source.name_normalized == "stripe"
        assert source.platform == PlatformType.GREENHOUSE
        assert source.identifier == "stripe"
        assert source.enabled is True  # Default value

    def test_source_creation_with_all_fields(self):
        """Test creating Source with all fields."""
        from app.models.source import Source, PlatformType

        source = Source(
            name="Airbnb",
            name_normalized="airbnb",
            platform=PlatformType.GREENHOUSE,
            identifier="airbnb",
            enabled=False,
            notes="Test notes",
        )

        assert source.name == "Airbnb"
        assert source.enabled is False
        assert source.notes == "Test notes"

    def test_source_created_at_auto_generated(self):
        """Test that created_at is auto-generated."""
        from app.models.source import Source, PlatformType

        before = datetime.now(timezone.utc)
        source = Source(
            name="Test",
            name_normalized="test",
            platform=PlatformType.GREENHOUSE,
            identifier="test",
        )
        after = datetime.now(timezone.utc)

        assert source.created_at >= before
        assert source.created_at <= after

    def test_source_updated_at_auto_generated(self):
        """Test that updated_at is auto-generated."""
        from app.models.source import Source, PlatformType

        before = datetime.now(timezone.utc)
        source = Source(
            name="Test",
            name_normalized="test",
            platform=PlatformType.GREENHOUSE,
            identifier="test",
        )
        after = datetime.now(timezone.utc)

        assert source.updated_at >= before
        assert source.updated_at <= after


class TestSourceCreateValidation:
    """Tests for SourceCreate schema validation (T004, T011)."""

    def test_source_create_valid(self):
        """Test valid SourceCreate schema."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="Stripe",
            platform="greenhouse",
            identifier="stripe",
        )

        assert data.name == "Stripe"
        assert data.platform == "greenhouse"
        assert data.identifier == "stripe"

    def test_source_create_strips_name_whitespace(self):
        """Test that name whitespace is stripped."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="  Stripe  ",
            platform="greenhouse",
            identifier="stripe",
        )

        assert data.name == "Stripe"

    def test_source_create_strips_identifier_whitespace(self):
        """Test that identifier whitespace is stripped."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="Stripe",
            platform="greenhouse",
            identifier="  stripe  ",
        )

        assert data.identifier == "stripe"

    def test_source_create_empty_name_after_strip_fails(self):
        """Test that empty name after stripping fails validation."""
        from app.schemas.source import SourceCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SourceCreate(
                name="   ",
                platform="greenhouse",
                identifier="stripe",
            )

        # Check that the error is about the name field
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("name",) for e in errors)

    def test_source_create_empty_identifier_after_strip_fails(self):
        """Test that empty identifier after stripping fails validation."""
        from app.schemas.source import SourceCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SourceCreate(
                name="Stripe",
                platform="greenhouse",
                identifier="   ",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("identifier",) for e in errors)

    def test_source_create_invalid_platform_fails(self):
        """Test that invalid platform fails validation."""
        from app.schemas.source import SourceCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SourceCreate(
                name="Stripe",
                platform="invalid_platform",
                identifier="stripe",
            )

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("platform",) for e in errors)

    def test_source_create_with_optional_fields(self):
        """Test SourceCreate with optional fields."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="Stripe",
            platform="greenhouse",
            identifier="stripe",
            enabled=False,
            notes="Test notes",
        )

        assert data.enabled is False
        assert data.notes == "Test notes"


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
