import asyncio
from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class TikTokFetcher(BaseFetcher):
    """Fetcher for TikTok Careers API."""

    API_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
    REQUEST_TIMEOUT_SECONDS = 60.0
    MAX_RETRIES = 3
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    RETRY_BACKOFF_SECONDS = 0.25
    PAGE_SIZE = 12
    VALID_IDENTIFIER = "tiktok"
    DEFAULT_HEADERS = {
        "accept": "*/*",
        "accept-language": "en-US",
        "content-type": "application/json",
        "website-path": "tiktok",
        "origin": "https://lifeattiktok.com",
        "referer": "https://lifeattiktok.com/",
        "user-agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/142.0.0.0 Safari/537.36"
        ),
    }

    @property
    def source_name(self) -> str:
        return "tiktok"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        _ = include_content
        self._validate_identifier(slug)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS),
            headers=dict(self.DEFAULT_HEADERS),
        ) as client:
            results: list[dict[str, Any]] = []
            offset = 0
            total: int | None = None

            while True:
                payload = await self._request_json(
                    client,
                    json={
                        "recruitment_id_list": [],
                        "job_category_id_list": [],
                        "subject_id_list": [],
                        "location_code_list": [],
                        "keyword": "",
                        "limit": self.PAGE_SIZE,
                        "offset": offset,
                    },
                )
                data = payload.get("data")
                if not isinstance(data, dict):
                    return results

                page_results = data.get("job_post_list")
                if not isinstance(page_results, list) or not page_results:
                    return results

                if total is None:
                    total = self._to_int_or_none(data.get("count"))

                results.extend(item for item in page_results if isinstance(item, dict))

                if total is not None and len(results) >= total:
                    return results[:total]

                offset += self.PAGE_SIZE

    def _validate_identifier(self, slug: str) -> None:
        if slug != self.VALID_IDENTIFIER:
            raise ValueError(f"Unsupported tiktok source identifier: {slug}")

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        *,
        json: dict[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.post(self.API_URL, json=json)
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retryable HTTP error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
                raise ValueError("TikTok response payload must be a JSON object")
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code not in self.RETRYABLE_STATUS_CODES or attempt + 1 >= self.MAX_RETRIES:
                    raise
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 >= self.MAX_RETRIES:
                    raise

            await asyncio.sleep(self.RETRY_BACKOFF_SECONDS * (2 ** attempt))

        if last_error is not None:
            raise last_error
        raise RuntimeError("TikTok request failed without an exception")

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
