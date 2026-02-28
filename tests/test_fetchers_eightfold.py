import pytest
import respx
from httpx import Response

from app.ingest.fetchers import EightfoldFetcher


class TestEightfoldFetcher:
    """EightfoldFetcher tests."""

    def test_source_name(self) -> None:
        fetcher = EightfoldFetcher()
        assert fetcher.source_name == "eightfold"

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_microsoft_paginates_and_merges_detail_payloads(self) -> None:
        search_route = respx.get("https://apply.careers.microsoft.com/api/pcsx/search").mock(
            side_effect=[
                Response(
                    200,
                    json={
                        "data": {
                            "count": 2,
                            "positions": [
                                {
                                    "id": "job-1",
                                    "name": "Software Engineer",
                                    "positionUrl": "/us/en/job/1",
                                    "locations": ["Toronto, ON, Canada"],
                                }
                            ],
                        }
                    },
                ),
                Response(
                    200,
                    json={
                        "data": {
                            "count": 2,
                            "positions": [
                                {
                                    "id": "job-2",
                                    "name": "Product Manager",
                                    "positionUrl": "/us/en/job/2",
                                    "locations": ["Remote"],
                                }
                            ],
                        }
                    },
                ),
            ]
        )
        detail_1 = respx.get("https://apply.careers.microsoft.com/api/pcsx/position_details").mock(
            side_effect=[
                Response(200, json={"data": {"jobDescription": "Build systems", "standardizedLocations": ["Toronto"]}}),
                Response(200, json={"data": {"jobDescription": "Shape roadmap", "standardizedLocations": ["Remote"]}}),
            ]
        )

        fetcher = EightfoldFetcher()
        result = await fetcher.fetch("microsoft")

        assert len(result) == 2
        assert result[0]["jobDescription"] == "Build systems"
        assert result[0]["standardizedLocations"] == ["Toronto"]
        assert result[0]["_board_base_url"] == "https://apply.careers.microsoft.com"
        assert result[1]["jobDescription"] == "Shape roadmap"
        assert search_route.call_count == 2
        assert detail_1.call_count == 2
        assert "domain=microsoft.com" in str(search_route.calls.last.request.url)
        assert "start=10" in str(search_route.calls.last.request.url)

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_include_content_false_skips_detail_requests(self) -> None:
        search_route = respx.get("https://apply.careers.microsoft.com/api/pcsx/search").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": "job-1",
                                "name": "Software Engineer",
                                "positionUrl": "/us/en/job/1",
                            }
                        ],
                    }
                },
            )
        )
        detail_route = respx.get("https://apply.careers.microsoft.com/api/pcsx/position_details").mock(
            return_value=Response(200, json={"data": {"jobDescription": "Build systems"}})
        )

        fetcher = EightfoldFetcher()
        result = await fetcher.fetch("microsoft", include_content=False)

        assert len(result) == 1
        assert "jobDescription" not in result[0]
        assert search_route.called
        assert detail_route.called is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_retries_retryable_detail_errors(self) -> None:
        respx.get("https://apply.careers.microsoft.com/api/pcsx/search").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": "job-1",
                                "name": "Software Engineer",
                                "positionUrl": "/us/en/job/1",
                            }
                        ],
                    }
                },
            )
        )
        detail_route = respx.get("https://apply.careers.microsoft.com/api/pcsx/position_details").mock(
            side_effect=[
                Response(500, json={"error": "server error"}),
                Response(200, json={"data": {"jobDescription": "Recovered"}}),
            ]
        )

        fetcher = EightfoldFetcher()
        result = await fetcher.fetch("microsoft")

        assert len(result) == 1
        assert result[0]["jobDescription"] == "Recovered"
        assert detail_route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_keeps_summary_when_detail_request_fails(self) -> None:
        respx.get("https://apply.careers.microsoft.com/api/pcsx/search").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": "job-1",
                                "name": "Software Engineer",
                                "positionUrl": "/us/en/job/1",
                                "locations": ["Toronto, ON, Canada"],
                            }
                        ],
                    }
                },
            )
        )
        respx.get("https://apply.careers.microsoft.com/api/pcsx/position_details").mock(
            return_value=Response(404, json={"error": "not found"})
        )

        fetcher = EightfoldFetcher()
        result = await fetcher.fetch("microsoft")

        assert len(result) == 1
        assert result[0]["id"] == "job-1"
        assert result[0]["_detail_fetch_failed"] is True
        assert "jobDescription" not in result[0]

    @pytest.mark.asyncio
    @respx.mock
    async def test_fetch_uses_nvidia_board_config(self) -> None:
        search_route = respx.get("https://nvidia.eightfold.ai/api/pcsx/search").mock(
            return_value=Response(
                200,
                json={
                    "data": {
                        "count": 1,
                        "positions": [
                            {
                                "id": "job-9",
                                "name": "GPU Architect",
                                "positionUrl": "/careers/job/9",
                            }
                        ],
                    }
                },
            )
        )

        fetcher = EightfoldFetcher()
        result = await fetcher.fetch("nvidia", include_content=False)

        assert len(result) == 1
        assert result[0]["_board_base_url"] == "https://nvidia.eightfold.ai"
        assert "domain=nvidia.com" in str(search_route.calls.last.request.url)

    @pytest.mark.asyncio
    async def test_fetch_unknown_slug_raises_value_error(self) -> None:
        fetcher = EightfoldFetcher()

        with pytest.raises(ValueError, match="Unsupported eightfold source identifier: unknown"):
            await fetcher.fetch("unknown")
