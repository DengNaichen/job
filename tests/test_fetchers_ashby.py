import pytest
import respx
from httpx import HTTPStatusError, Response

from app.ingest.fetchers import AshbyFetcher


class TestAshbyFetcher:
    """AshbyFetcher tests."""

    def test_source_name(self):
        fetcher = AshbyFetcher()
        assert fetcher.source_name == "ashby"

    def test_base_url(self):
        fetcher = AshbyFetcher()
        assert fetcher.BASE_URL == "https://api.ashbyhq.com/posting-api/job-board"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_jobs(self):
        respx.get("https://api.ashbyhq.com/posting-api/job-board/test-company").mock(
            return_value=Response(200, json={"apiVersion": "1", "jobs": [{"id": "job-1"}, {"id": "job-2"}]})
        )

        fetcher = AshbyFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 2
        assert result[0]["id"] == "job-1"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_include_compensation_true(self):
        route = respx.get("https://api.ashbyhq.com/posting-api/job-board/test-company").mock(
            return_value=Response(200, json={"jobs": []})
        )

        fetcher = AshbyFetcher()
        await fetcher.fetch("test-company", include_content=True)

        assert route.called
        request = route.calls.last.request
        assert "includeCompensation=true" in str(request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_with_include_compensation_false(self):
        route = respx.get("https://api.ashbyhq.com/posting-api/job-board/test-company").mock(
            return_value=Response(200, json={"jobs": []})
        )

        fetcher = AshbyFetcher()
        await fetcher.fetch("test-company", include_content=False)

        assert route.called
        request = route.calls.last.request
        assert "includeCompensation=false" in str(request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_missing_jobs_key(self):
        respx.get("https://api.ashbyhq.com/posting-api/job-board/test-company").mock(
            return_value=Response(200, json={"apiVersion": "1"})
        )

        fetcher = AshbyFetcher()
        result = await fetcher.fetch("test-company")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_raises_for_not_found(self):
        respx.get("https://api.ashbyhq.com/posting-api/job-board/missing").mock(
            return_value=Response(404, text="Not Found")
        )

        fetcher = AshbyFetcher()

        with pytest.raises(HTTPStatusError):
            await fetcher.fetch("missing")
