"""
Unit tests for Source model.

Covers:
- normalize_name utility (T002)
- PlatformType enum (T002)
- Source SQLModel entity construction and defaults (T003)
"""

import pytest
from datetime import datetime, timezone


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
        assert PlatformType.ASHBY.value == "ashby"
        assert PlatformType.SMARTRECRUITERS.value == "smartrecruiters"
        assert PlatformType.EIGHTFOLD.value == "eightfold"
        assert PlatformType.APPLE.value == "apple"
        assert PlatformType.UBER.value == "uber"
        assert PlatformType.TIKTOK.value == "tiktok"

    def test_platform_type_from_string(self):
        """Test creating PlatformType from string."""
        from app.models.source import PlatformType

        assert PlatformType("greenhouse") == PlatformType.GREENHOUSE
        assert PlatformType("lever") == PlatformType.LEVER
        assert PlatformType("workday") == PlatformType.WORKDAY
        assert PlatformType("github") == PlatformType.GITHUB
        assert PlatformType("ashby") == PlatformType.ASHBY
        assert PlatformType("smartrecruiters") == PlatformType.SMARTRECRUITERS
        assert PlatformType("eightfold") == PlatformType.EIGHTFOLD
        assert PlatformType("apple") == PlatformType.APPLE
        assert PlatformType("uber") == PlatformType.UBER
        assert PlatformType("tiktok") == PlatformType.TIKTOK

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
