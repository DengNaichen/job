import asyncio
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
    MAX_RETRIES = 3
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    RETRY_BACKOFF_SECONDS = 0.25
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
        response = await self._request(client, method="GET", url=f"{self.API_BASE}{self.CSRF_PATH}")
        token = response.headers.get("x-apple-csrf-token")
        if not token:
            raise ValueError("Apple CSRF token missing from response headers")
        return token

    async def _fetch_all_summaries(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        total_records: int | None = None
        page = 1

        while True:
            payload = await self._request_json(
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
        semaphore = asyncio.Semaphore(self.DETAIL_CONCURRENCY)

        async def fetch_detail(summary: dict[str, Any]) -> dict[str, Any]:
            position_id = summary.get("positionId")
            if not isinstance(position_id, str) or not position_id.strip():
                failed_summary = dict(summary)
                failed_summary["_detail_fetch_failed"] = True
                return failed_summary

            async with semaphore:
                try:
                    payload = await self._request_json(
                        client,
                        method="GET",
                        url=f"{self.API_BASE}{self.DETAIL_PATH}/{position_id.strip()}",
                    )
                except Exception:
                    failed_summary = dict(summary)
                    failed_summary["_detail_fetch_failed"] = True
                    return failed_summary

            detail = payload.get("res")
            if not isinstance(detail, dict):
                failed_summary = dict(summary)
                failed_summary["_detail_fetch_failed"] = True
                return failed_summary

            merged = dict(summary)
            merged.update(detail)
            return merged

        return await asyncio.gather(*(fetch_detail(summary) for summary in summaries))

    async def _request_json(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self._request(client, method=method, url=url, json=json)
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        raise ValueError("Apple response payload must be a JSON object")

    async def _request(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.request(method, url, json=json)
                if response.status_code in self.RETRYABLE_STATUS_CODES:
                    raise httpx.HTTPStatusError(
                        f"Retryable HTTP error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if (
                    exc.response.status_code not in self.RETRYABLE_STATUS_CODES
                    or attempt + 1 >= self.MAX_RETRIES
                ):
                    raise
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 >= self.MAX_RETRIES:
                    raise

            await asyncio.sleep(self.RETRY_BACKOFF_SECONDS * (2**attempt))

        if last_error is not None:
            raise last_error
        raise RuntimeError("Apple request failed without an exception")

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
