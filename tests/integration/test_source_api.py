"""
Integration tests for Source API endpoints.

Tests for MVP User Story 1 (T016):
- POST /api/v1/sources - Create source
  - Success: create new source
  - Failure: duplicate name
  - Failure: unsupported platform
  - Failure: blank identifier
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import engine
from app.models import SyncRun, SyncRunStatus, build_source_key


class TestCreateSource:
    """Integration tests for POST /api/v1/sources endpoint."""

    def test_create_source_success(self, client: TestClient):
        """Test successful source creation."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Stripe",
                "platform": "greenhouse",
                "identifier": "stripe",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Stripe"
        assert data["data"]["platform"] == "greenhouse"
        assert data["data"]["identifier"] == "stripe"
        assert data["data"]["enabled"] is True  # Default
        assert "id" in data["data"]
        assert "created_at" in data["data"]

    def test_create_source_eightfold_success(self, client: TestClient):
        """Test successful eightfold source creation."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Microsoft",
                "platform": "eightfold",
                "identifier": "microsoft",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["platform"] == "eightfold"
        assert data["data"]["identifier"] == "microsoft"

    def test_create_source_with_all_fields(self, client: TestClient):
        """Test creating source with all optional fields."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Airbnb",
                "platform": "greenhouse",
                "identifier": "airbnb",
                "enabled": False,
                "notes": "Test company",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["data"]["name"] == "Airbnb"
        assert data["data"]["enabled"] is False
        assert data["data"]["notes"] == "Test company"

    def test_create_source_duplicate_name_fails(self, client: TestClient):
        """Test that duplicate name on same platform is rejected."""
        # Create first source
        client.post(
            "/api/v1/sources",
            json={
                "name": "Stripe",
                "platform": "greenhouse",
                "identifier": "stripe",
            },
        )

        # Try to create with same name (different case)
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "STRIPE",
                "platform": "greenhouse",
                "identifier": "stripe-2",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False
        assert "duplicate" in data["error"]["message"].lower() or "already exists" in data["error"]["message"].lower()

    def test_create_source_duplicate_name_with_whitespace_fails(self, client: TestClient):
        """Test that duplicate name with whitespace is rejected on same platform."""
        # Create first source
        client.post(
            "/api/v1/sources",
            json={
                "name": "Stripe",
                "platform": "greenhouse",
                "identifier": "stripe",
            },
        )

        # Try to create with same name (with whitespace)
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "  stripe  ",
                "platform": "greenhouse",
                "identifier": "stripe-2",
            },
        )

        assert response.status_code == 409
        data = response.json()
        assert data["success"] is False

    def test_create_source_same_name_different_platform_success(self, client: TestClient):
        """Test that same company name across different platforms is allowed."""
        company_name = "Stripe Multi Platform Co"
        response_1 = client.post(
            "/api/v1/sources",
            json={
                "name": company_name,
                "platform": "greenhouse",
                "identifier": "stripe-multi-gh",
            },
        )
        assert response_1.status_code == 201

        response_2 = client.post(
            "/api/v1/sources",
            json={
                "name": company_name,
                "platform": "lever",
                "identifier": "stripe-multi-lever",
            },
        )
        assert response_2.status_code == 201

    def test_create_source_unsupported_platform_fails(self, client: TestClient):
        """Test that unsupported platform is rejected."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Test Company",
                "platform": "unsupported_platform",
                "identifier": "test",
            },
        )

        assert response.status_code == 422
        data = response.json()
        # Validation error from Pydantic
        assert "detail" in data or "error" in data

    def test_create_source_blank_identifier_fails(self, client: TestClient):
        """Test that blank identifier is rejected."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Test Company",
                "platform": "greenhouse",
                "identifier": "   ",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data or "error" in data

    def test_create_source_blank_name_fails(self, client: TestClient):
        """Test that blank name is rejected."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "   ",
                "platform": "greenhouse",
                "identifier": "test",
            },
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data or "error" in data

    def test_create_source_missing_required_fields_fails(self, client: TestClient):
        """Test that missing required fields are rejected."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Test Company",
                # missing platform
                "identifier": "test",
            },
        )

        assert response.status_code == 422

    def test_create_source_normalizes_name(self, client: TestClient):
        """Test that name is stored as-is but uniqueness is case-insensitive."""
        # Create source with mixed case name
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "  Stripe Inc Unique  ",
                "platform": "greenhouse",
                "identifier": "stripe-inc-unique",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Name should be stripped of whitespace
        assert data["data"]["name"] == "Stripe Inc Unique"

    def test_create_source_validates_platform_values(self, client: TestClient):
        """Test that only valid platform values are accepted."""
        valid_platforms = [
            "greenhouse",
            "lever",
            "workday",
            "github",
            "ashby",
            "smartrecruiters",
            "eightfold",
            "apple",
            "uber",
            "tiktok",
        ]

        for platform in valid_platforms:
            response = client.post(
                "/api/v1/sources",
                json={
                    "name": f"Company {platform}",
                    "platform": platform,
                    "identifier": f"company-{platform}",
                },
            )

            assert response.status_code == 201, f"Platform {platform} should be valid"


class TestListSourceQueries:
    """Integration tests for source list query behavior."""

    def test_list_sources_can_filter_by_platform(self, client: TestClient):
        """List endpoint supports platform filter for greenhouse test setup."""
        client.post(
            "/api/v1/sources",
            json={"name": "Stripe", "platform": "greenhouse", "identifier": "stripe"},
        )
        client.post(
            "/api/v1/sources",
            json={"name": "OpenAI", "platform": "ashby", "identifier": "openai"},
        )

        response = client.get("/api/v1/sources", params={"platform": "greenhouse"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["total"] >= 1
        assert all(item["platform"] == "greenhouse" for item in payload["data"])

    def test_list_source_slugs_for_greenhouse(self, client: TestClient):
        """Dedicated slug endpoint returns identifiers for target platform."""
        client.post(
            "/api/v1/sources",
            json={"name": "Cloudflare", "platform": "greenhouse", "identifier": "cloudflare"},
        )
        client.post(
            "/api/v1/sources",
            json={"name": "Stripe", "platform": "greenhouse", "identifier": "stripe"},
        )
        client.post(
            "/api/v1/sources",
            json={"name": "OpenAI", "platform": "ashby", "identifier": "openai"},
        )

        response = client.get("/api/v1/sources/slugs", params={"platform": "greenhouse"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["success"] is True
        assert payload["platform"] == "greenhouse"
        assert "cloudflare" in payload["data"]
        assert "stripe" in payload["data"]
        assert "openai" not in payload["data"]


class TestSourceAPIResponseFormat:
    """Tests for API response format compliance."""

    def test_success_response_format(self, client: TestClient):
        """Test that successful response follows the expected format."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Response Test",
                "platform": "greenhouse",
                "identifier": "response-test",
            },
        )

        assert response.status_code == 201
        data = response.json()

        # Response should have success flag
        assert "success" in data
        assert data["success"] is True

        # Response should have data object
        assert "data" in data
        assert isinstance(data["data"], dict)

        # Data should have expected fields
        expected_fields = ["id", "name", "platform", "identifier", "enabled", "created_at", "updated_at"]
        for field in expected_fields:
            assert field in data["data"], f"Missing field: {field}"

    def test_error_response_format(self, client: TestClient):
        """Test that error response follows the expected format."""
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "   ",  # Invalid: blank name
                "platform": "greenhouse",
                "identifier": "test",
            },
        )

        assert response.status_code == 422
        data = response.json()

        # Pydantic validation errors have "detail" field
        # Custom business errors have "success" and "error" fields
        # Either format is acceptable for validation errors
        assert "detail" in data or ("success" in data and data["success"] is False)


class TestDeleteSource:
    """Integration tests for DELETE /api/v1/sources."""

    def test_delete_source_success(self, client: TestClient):
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Delete Me",
                "platform": "greenhouse",
                "identifier": "delete-me",
            },
        )
        source_id = response.json()["data"]["id"]

        delete_response = client.delete(f"/api/v1/sources/{source_id}")

        assert delete_response.status_code == 200
        payload = delete_response.json()
        assert payload["success"] is True

    def test_delete_source_with_sync_runs_fails(self, client: TestClient):
        response = client.post(
            "/api/v1/sources",
            json={
                "name": "Protected Source",
                "platform": "greenhouse",
                "identifier": "protected-source",
            },
        )
        payload = response.json()["data"]
        source_id = payload["id"]

        async def seed_sync_run() -> None:
            async with AsyncSession(engine) as session:
                session.add(
                    SyncRun(
                        source=build_source_key("greenhouse", "protected-source"),
                        status=SyncRunStatus.success,
                    )
                )
                await session.commit()

        asyncio.run(seed_sync_run())

        delete_response = client.delete(f"/api/v1/sources/{source_id}")

        assert delete_response.status_code == 409
        error_payload = delete_response.json()
        assert error_payload["success"] is False
        assert error_payload["error"]["code"] == "HAS_REFERENCES"
