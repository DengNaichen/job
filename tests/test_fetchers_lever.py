import pytest
import respx
from httpx import Response

from app.ingest.fetchers import LeverFetcher


class TestLeverFetcher:
    """LeverFetcher tests."""

    def test_source_name(self):
        fetcher = LeverFetcher()
        assert fetcher.source_name == "lever"

    def test_base_url(self):
        fetcher = LeverFetcher()
        assert fetcher.BASE_URL == "https://api.lever.co/v0/postings"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_jobs(self):
        route = respx.get("https://api.lever.co/v0/postings/test-company").mock(
            return_value=Response(200, json=[{"id": "1", "text": "Engineer"}, {"id": "2", "text": "Designer"}])
        )

        fetcher = LeverFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 2
        assert result[0]["text"] == "Engineer"
        assert route.called
        assert "mode=json" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_accepts_include_content_flag(self):
        route = respx.get("https://api.lever.co/v0/postings/test-company").mock(
            return_value=Response(200, json=[])
        )

        fetcher = LeverFetcher()
        result = await fetcher.fetch("test-company", include_content=False)

        assert result == []
        assert route.called
        assert "mode=json" in str(route.calls.last.request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_empty_jobs(self):
        respx.get("https://api.lever.co/v0/postings/empty").mock(return_value=Response(200, json=[]))

        fetcher = LeverFetcher()
        result = await fetcher.fetch("empty")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_non_list_payload(self):
        respx.get("https://api.lever.co/v0/postings/test-company").mock(
            return_value=Response(200, json={"error": "unexpected"})
        )

        fetcher = LeverFetcher()
        result = await fetcher.fetch("test-company")

        assert result == []
