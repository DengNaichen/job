import pytest
import respx
from httpx import Response

from app.ingest.fetchers import GitHubRepoFetcher


class TestGitHubRepoFetcher:
    def test_source_name(self):
        fetcher = GitHubRepoFetcher()
        assert fetcher.source_name == "github"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_from_json_list(self):
        respx.get(
            "https://raw.githubusercontent.com/acme/jobs/main/data/jobs.json"
        ).mock(
            return_value=Response(
                200,
                json=[
                    {"id": "1", "title": "Engineer"},
                    {"id": "2", "title": "Designer"},
                ],
            )
        )

        fetcher = GitHubRepoFetcher()
        result = await fetcher.fetch("acme/jobs:data/jobs.json")
        assert len(result) == 2
        assert result[0]["title"] == "Engineer"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_from_jobs_key(self):
        respx.get(
            "https://raw.githubusercontent.com/acme/jobs/main/data/jobs.json"
        ).mock(return_value=Response(200, json={"jobs": [{"id": "1", "title": "Engineer"}]}))

        fetcher = GitHubRepoFetcher()
        result = await fetcher.fetch("acme/jobs:data/jobs.json")
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_invalid_slug_raises_error(self):
        fetcher = GitHubRepoFetcher()
        with pytest.raises(ValueError):
            fetcher._parse_slug("acme/jobs")
