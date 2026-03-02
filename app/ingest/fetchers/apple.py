from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class AppleFetcher(BaseFetcher):
    """Fetcher for Apple Jobs API."""

    BASE_URL = "https://jobs.apple.com"
    API_BASE = f"{BASE_URL}/api/v1"
    SEARCH_PATH = "/search"
    CSRF_PATH = "/CSRFToken"
    DETAIL_PATH = "/jobDetails"
    LOCALE = "en-us"
    PAGE_SIZE = 20
    REQUEST_TIMEOUT_SECONDS = 60.0
    DETAIL_CONCURRENCY = 6
    VALID_IDENTIFIER = "apple"
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/{LOCALE}/search",
        "Content-Type": "application/json",
        "browserlocale": LOCALE,
        "locale": "EN_US",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    @property
    def source_name(self) -> str:
        return "apple"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        self._validate_identifier(slug)

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS),
            headers=dict(self.DEFAULT_HEADERS),
        ) as client:
            csrf_token = await self._get_csrf_token(client)
            client.headers["x-apple-csrf-token"] = csrf_token

            summaries = await self._fetch_all_summaries(client)
            if not include_content or not summaries:
                return summaries
            return await self._fetch_all_details(client, summaries)

    def _validate_identifier(self, slug: str) -> None:
        if slug != self.VALID_IDENTIFIER:
            raise ValueError(f"Unsupported apple source identifier: {slug}")

    async def _get_csrf_token(self, client: httpx.AsyncClient) -> str:
        response = await self.request_with_retry(
            client, method="GET", url=f"{self.API_BASE}{self.CSRF_PATH}"
        )
        token = response.headers.get("x-apple-csrf-token")
        if not token:
            raise ValueError("Apple CSRF token missing from response headers")
        return token

    async def _fetch_all_summaries(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        total_records: int | None = None
        page = 1

        while True:
            payload = await self.request_json_with_retry(
                client,
                method="POST",
                url=f"{self.API_BASE}{self.SEARCH_PATH}",
                json={
                    "query": "",
                    "filters": {},
                    "page": page,
                    "locale": self.LOCALE,
                    "sort": "",
                    "format": {
                        "longDate": "MMMM D, YYYY",
                        "mediumDate": "MMM D, YYYY",
                    },
                },
            )
            data = payload.get("res")
            if not isinstance(data, dict):
                return summaries

            results = data.get("searchResults")
            if not isinstance(results, list) or not results:
                return summaries

            if total_records is None:
                total_records = self._to_int_or_none(data.get("totalRecords"))

            for item in results:
                if not isinstance(item, dict):
                    continue
                normalized = dict(item)
                normalized["_locale"] = self.LOCALE
                summaries.append(normalized)

            if total_records is not None and len(summaries) >= total_records:
                return summaries[:total_records]

            page += 1

    async def _fetch_all_details(
        self,
        client: httpx.AsyncClient,
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        async def fetch_detail(
            client: httpx.AsyncClient, summary: dict[str, Any]
        ) -> dict[str, Any] | None:
            position_id = summary.get("positionId")
            if not isinstance(position_id, str) or not position_id.strip():
                return None

            try:
                payload = await self.request_json_with_retry(
                    client,
                    method="GET",
                    url=f"{self.API_BASE}{self.DETAIL_PATH}/{position_id.strip()}",
                )
            except Exception:
                return None

            detail = payload.get("res")
            if not isinstance(detail, dict):
                return None

            merged = dict(summary)
            merged.update(detail)
            return merged

        def on_failure(summary: dict[str, Any]) -> dict[str, Any]:
            failed = dict(summary)
            failed["_detail_fetch_failed"] = True
            return failed

        return await self.fetch_details_concurrently(
            client,
            summaries,
            fetch_detail=fetch_detail,
            concurrency=self.DETAIL_CONCURRENCY,
            on_failure=on_failure,
        )
