import json

import pytest
import respx
from httpx import Response

from app.ingest.fetchers import AppleFetcher, TikTokFetcher, UberFetcher


class TestAppleFetcher:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_paginates_and_merges_detail_payloads(self) -> None:
        csrf_route = respx.get("https://jobs.apple.com/api/v1/CSRFToken").mock(
            return_value=Response(200, headers={"x-apple-csrf-token": "token-123"})
        )
        search_route = respx.post("https://jobs.apple.com/api/v1/search").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "res": {
                            "totalRecords": 2,
                            "searchResults": [
                                {
                                    "positionId": "job-1",
                                    "postingTitle": "Specialist",
                                    "transformedPostingTitle": "specialist",
                                }
                            ],
                        }
                    },
                ),
                Response(
                    200,
                    json={
                        "res": {
                            "totalRecords": 2,
                            "searchResults": [
                                {
                                    "positionId": "job-2",
                                    "postingTitle": "Engineer",
                                    "transformedPostingTitle": "engineer",
                                }
                            ],
                        }
                    },
                ),
            ]
        )
        detail_1 = respx.get("https://jobs.apple.com/api/v1/jobDetails/job-1").mock(
            return_value=Response(200, json={"res": {"description": "Help customers"}})
        )
        detail_2 = respx.get("https://jobs.apple.com/api/v1/jobDetails/job-2").mock(
            return_value=Response(200, json={"res": {"description": "Build systems"}})
        )

        fetcher = AppleFetcher()
        result = await fetcher.fetch("apple")

        assert len(result) == 2
        assert result[0]["description"] == "Help customers"
        assert result[1]["description"] == "Build systems"
        assert result[0]["_locale"] == "en-us"
        assert csrf_route.called
        assert search_route.call_count == 2
        assert detail_1.called
        assert detail_2.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_include_content_false_skips_detail_requests(self) -> None:
        respx.get("https://jobs.apple.com/api/v1/CSRFToken").mock(
            return_value=Response(200, headers={"x-apple-csrf-token": "token-123"})
        )
        search_route = respx.post("https://jobs.apple.com/api/v1/search").mock(
            return_value=Response(
                200,
                json={"res": {"totalRecords": 1, "searchResults": [{"positionId": "job-1", "postingTitle": "Specialist"}]}},
            )
        )
        detail_route = respx.get("https://jobs.apple.com/api/v1/jobDetails/job-1").mock(
            return_value=Response(200, json={"res": {"description": "Help customers"}})
        )

        fetcher = AppleFetcher()
        result = await fetcher.fetch("apple", include_content=False)

        assert len(result) == 1
        assert "description" not in result[0]
        assert search_route.called
        assert detail_route.called is False

    @pytest.mark.asyncio
    async def test_fetch_unknown_identifier_raises_value_error(self) -> None:
        fetcher = AppleFetcher()
        with pytest.raises(ValueError, match="Unsupported apple source identifier: other"):
            await fetcher.fetch("other")


class TestUberFetcher:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_paginates_results(self) -> None:
        route = respx.post("https://www.uber.com/api/loadSearchJobsResults").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "status": "success",
                        "data": {
                            "results": [{"id": 1, "title": "Engineer"}],
                            "totalResults": {"low": 2},
                        },
                    },
                ),
                Response(
                    200,
                    json={
                        "status": "success",
                        "data": {
                            "results": [{"id": 2, "title": "Designer"}],
                            "totalResults": {"low": 2},
                        },
                    },
                ),
            ]
        )

        fetcher = UberFetcher()
        result = await fetcher.fetch("uber")

        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2
        assert route.call_count == 2
        last_body = json.loads(route.calls.last.request.content.decode())
        assert last_body["page"] == 1

    @pytest.mark.asyncio
    async def test_fetch_unknown_identifier_raises_value_error(self) -> None:
        fetcher = UberFetcher()
        with pytest.raises(ValueError, match="Unsupported uber source identifier: other"):
            await fetcher.fetch("other")


class TestTikTokFetcher:
    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_paginates_results(self) -> None:
        route = respx.post("https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts").mock(
            side_effect=[
                Response(
                    200,
                    json={"data": {"count": 2, "job_post_list": [{"id": "1", "title": "Policy Manager"}]}},
                ),
                Response(
                    200,
                    json={"data": {"count": 2, "job_post_list": [{"id": "2", "title": "Product Counsel"}]}},
                ),
            ]
        )

        fetcher = TikTokFetcher()
        result = await fetcher.fetch("tiktok")

        assert len(result) == 2
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"
        assert route.call_count == 2
        last_body = json.loads(route.calls.last.request.content.decode())
        assert last_body["offset"] == 12

    @pytest.mark.asyncio
    async def test_fetch_unknown_identifier_raises_value_error(self) -> None:
        fetcher = TikTokFetcher()
        with pytest.raises(ValueError, match="Unsupported tiktok source identifier: other"):
            await fetcher.fetch("other")
