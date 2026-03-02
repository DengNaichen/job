"""
Unit tests for Source schemas.

Covers:
- SourceCreate validation (T004, T011)
"""

import pytest


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

    def test_source_create_accepts_eightfold_platform(self):
        """Test SourceCreate schema accepts eightfold."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="Microsoft",
            platform="eightfold",
            identifier="microsoft",
        )

        assert data.platform.value == "eightfold"

    def test_source_create_accepts_apple_platform(self):
        """Test SourceCreate schema accepts apple."""
        from app.schemas.source import SourceCreate

        data = SourceCreate(
            name="Apple",
            platform="apple",
            identifier="apple",
        )

        assert data.platform.value == "apple"

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
