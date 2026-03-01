import pytest
import respx
from httpx import Response

from app.ingest.fetchers import GreenhouseFetcher


class TestGreenhouseFetcher:
    """GreenhouseFetcher tests."""

    def test_source_name(self):
        fetcher = GreenhouseFetcher()
        assert fetcher.source_name == "greenhouse"

    def test_base_url(self):
        fetcher = GreenhouseFetcher()
        assert fetcher.BASE_URL == "https://boards-api.greenhouse.io/v1/boards"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_jobs(self):
        """Test normal job list return."""
        respx.get("https://boards-api.greenhouse.io/v1/boards/test-company/jobs").mock(
            return_value=Response(
                200, json={"jobs": [{"id": 1, "title": "Engineer"}, {"id": 2, "title": "Designer"}]}
            )
        )

        fetcher = GreenhouseFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 2
        assert result[0]["title"] == "Engineer"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_include_content_true(self):
        """Test include_content=True parameter."""
        route = respx.get("https://boards-api.greenhouse.io/v1/boards/test-company/jobs").mock(
            return_value=Response(200, json={"jobs": []})
        )

        fetcher = GreenhouseFetcher()
        await fetcher.fetch("test-company", include_content=True)

        assert route.called
        request = route.calls.last.request
        assert "content=true" in str(request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_include_content_false(self):
        """Test include_content=False parameter."""
        route = respx.get("https://boards-api.greenhouse.io/v1/boards/test-company/jobs").mock(
            return_value=Response(200, json={"jobs": []})
        )

        fetcher = GreenhouseFetcher()
        await fetcher.fetch("test-company", include_content=False)

        assert route.called
        request = route.calls.last.request
        assert "content=false" in str(request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_empty_jobs(self):
        """Test empty job list."""
        respx.get("https://boards-api.greenhouse.io/v1/boards/empty/jobs").mock(
            return_value=Response(200, json={"jobs": []})
        )

        fetcher = GreenhouseFetcher()
        result = await fetcher.fetch("empty")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_missing_jobs_key(self):
        """Test response missing jobs key."""
        respx.get("https://boards-api.greenhouse.io/v1/boards/test-company/jobs").mock(
            return_value=Response(200, json={"error": "not found"})
        )

        fetcher = GreenhouseFetcher()
        result = await fetcher.fetch("test-company")

        assert result == []
