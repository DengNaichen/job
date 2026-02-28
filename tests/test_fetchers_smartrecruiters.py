import pytest
import respx
from httpx import Response

from app.ingest.fetchers import SmartRecruitersFetcher


class TestSmartRecruitersFetcher:
    """SmartRecruitersFetcher tests."""

    def test_source_name(self):
        fetcher = SmartRecruitersFetcher()
        assert fetcher.source_name == "smartrecruiters"

    def test_base_url(self):
        fetcher = SmartRecruitersFetcher()
        assert fetcher.BASE_URL == "https://api.smartrecruiters.com/v1/companies"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_paginates_and_merges_detail_payloads(self):
        list_route = respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "offset": 0,
                        "limit": 1,
                        "totalFound": 2,
                        "content": [
                            {
                                "id": "job-1",
                                "name": "Engineer",
                                "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1",
                            }
                        ],
                    },
                ),
                Response(
                    200,
                    json={
                        "offset": 1,
                        "limit": 1,
                        "totalFound": 2,
                        "content": [
                            {
                                "id": "job-2",
                                "name": "Designer",
                                "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-2",
                            }
                        ],
                    },
                ),
            ]
        )
        detail_1 = respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1").mock(
            return_value=Response(200, json={"id": "job-1", "applyUrl": "https://apply/1", "jobAd": {"sections": {}}})
        )
        detail_2 = respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-2").mock(
            return_value=Response(200, json={"id": "job-2", "applyUrl": "https://apply/2", "jobAd": {"sections": {}}})
        )

        fetcher = SmartRecruitersFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 2
        assert result[0]["applyUrl"] == "https://apply/1"
        assert result[1]["applyUrl"] == "https://apply/2"
        assert list_route.call_count == 2
        assert detail_1.called
        assert detail_2.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_accepts_include_content_flag(self):
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings").mock(
            return_value=Response(
                200,
                json={
                    "offset": 0,
                    "limit": 100,
                    "totalFound": 1,
                    "content": [
                        {
                            "id": "job-1",
                            "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1",
                        }
                    ],
                },
            )
        )
        detail = respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1").mock(
            return_value=Response(200, json={"id": "job-1", "applyUrl": "https://apply/1"})
        )

        fetcher = SmartRecruitersFetcher()
        result = await fetcher.fetch("test-company", include_content=False)

        assert len(result) == 1
        assert detail.called

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_returns_empty_list_for_missing_content(self):
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings").mock(
            return_value=Response(200, json={"offset": 0, "limit": 100, "totalFound": 0})
        )

        fetcher = SmartRecruitersFetcher()
        result = await fetcher.fetch("test-company")

        assert result == []

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_skips_missing_detail_records(self):
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings").mock(
            return_value=Response(
                200,
                json={
                    "offset": 0,
                    "limit": 2,
                    "totalFound": 2,
                    "content": [
                        {
                            "id": "job-1",
                            "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1",
                        },
                        {
                            "id": "job-2",
                            "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-2",
                        },
                    ],
                },
            )
        )
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1").mock(
            return_value=Response(404, json={"error": "not found"})
        )
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-2").mock(
            return_value=Response(200, json={"id": "job-2", "applyUrl": "https://apply/2", "jobAd": {"sections": {}}})
        )

        fetcher = SmartRecruitersFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 1
        assert result[0]["id"] == "job-2"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_retries_retryable_detail_errors(self):
        respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings").mock(
            return_value=Response(
                200,
                json={
                    "offset": 0,
                    "limit": 1,
                    "totalFound": 1,
                    "content": [
                        {
                            "id": "job-1",
                            "ref": "https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1",
                        }
                    ],
                },
            )
        )
        detail_route = respx.get("https://api.smartrecruiters.com/v1/companies/test-company/postings/job-1").mock(
            side_effect=[
                Response(500, json={"error": "server error"}),
                Response(200, json={"id": "job-1", "applyUrl": "https://apply/1", "jobAd": {"sections": {}}}),
            ]
        )

        fetcher = SmartRecruitersFetcher()
        result = await fetcher.fetch("test-company")

        assert len(result) == 1
        assert result[0]["applyUrl"] == "https://apply/1"
        assert detail_route.call_count == 2
