import asyncio
from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class UberFetcher(BaseFetcher):
    """Fetcher for Uber Careers API."""

    API_URL = "https://www.uber.com/api/loadSearchJobsResults"
    REQUEST_TIMEOUT_SECONDS = 60.0
    PAGE_SIZE = 50
    VALID_IDENTIFIER = "uber"
    DEFAULT_HEADERS = {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": "https://www.uber.com",
        "Referer": "https://www.uber.com/us/en/careers/",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "x-csrf-token": "x",
        "x-uber-sites-page-edge-cache-enabled": "true",
    }

    @property
    def source_name(self) -> str:
        return "uber"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        _ = include_content
        self._validate_identifier(slug)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS),
            headers=dict(self.DEFAULT_HEADERS),
        ) as client:
            results: list[dict[str, Any]] = []
            page = 0
            total: int | None = None

            while True:
                payload = await self.request_json_with_retry(
                    client,
                    method="POST",
                    url=self.API_URL,
                    params={"localeCode": "en"},
                    json={
                        "limit": self.PAGE_SIZE,
                        "page": page,
                        "params": {
                            "department": [],
                            "lineOfBusinessName": [],
                            "location": [],
                            "programAndPlatform": [],
                            "team": [],
                        },
                    },
                )
                if payload.get("status") != "success":
                    raise ValueError(f"Uber API returned non-success status: {payload}")

                data = payload.get("data")
                if not isinstance(data, dict):
                    return results

                page_results = data.get("results")
                if not isinstance(page_results, list) or not page_results:
                    return results

                if total is None:
                    total = self._extract_total(data.get("totalResults"))

                results.extend(item for item in page_results if isinstance(item, dict))

                if total is not None and len(results) >= total:
                    return results[:total]
                if total is None and len(page_results) < self.PAGE_SIZE:
                    return results

                page += 1

    def _validate_identifier(self, slug: str) -> None:
        if slug != self.VALID_IDENTIFIER:
            raise ValueError(f"Unsupported uber source identifier: {slug}")

    @staticmethod
    def _extract_total(value: Any) -> int | None:
        if isinstance(value, dict):
            value = value.get("low")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
