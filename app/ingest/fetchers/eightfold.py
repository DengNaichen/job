import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class EightfoldFetcher(BaseFetcher):
    """Fetcher for company-specific Eightfold job boards."""

    BOARD_CONFIGS: Mapping[str, dict[str, str]] = {
        "microsoft": {
            "base_url": "https://apply.careers.microsoft.com",
            "domain": "microsoft.com",
        },
        "nvidia": {
            "base_url": "https://nvidia.eightfold.ai",
            "domain": "nvidia.com",
        },
    }
    SEARCH_PATH = "/api/pcsx/search"
    DETAIL_PATH = "/api/pcsx/position_details"
    PAGE_SIZE = 10
    REQUEST_TIMEOUT_SECONDS = 60.0
    MAX_RETRIES = 3
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    RETRY_BACKOFF_SECONDS = 0.25
    DETAIL_CONCURRENCY = 6
    MAX_CONSECUTIVE_EMPTY_PAGES = 2

    @property
    def source_name(self) -> str:
        return "eightfold"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        config = self._get_board_config(slug)

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS)) as client:
            summaries = await self._fetch_all_summaries(client, config)
            if not include_content or not summaries:
                return summaries
            return await self._fetch_all_details(client, config, summaries)

    def _get_board_config(self, slug: str) -> dict[str, str]:
        config = self.BOARD_CONFIGS.get(slug)
        if config is None:
            raise ValueError(f"Unsupported eightfold source identifier: {slug}")
        return config

    async def _fetch_all_summaries(
        self,
        client: httpx.AsyncClient,
        config: dict[str, str],
    ) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        total_count: int | None = None
        start = 0
        consecutive_empty_pages = 0

        while True:
            payload = await self._request_json(
                client,
                url=f"{config['base_url']}{self.SEARCH_PATH}",
                params={
                    "domain": config["domain"],
                    "query": "",
                    "location": "",
                    "start": start,
                    "sort_by": "timestamp",
                },
            )
            data = payload.get("data")
            positions = self._extract_positions(data)
            if total_count is None and isinstance(data, dict):
                total_count = self._to_int_or_none(data.get("count"))

            if not positions:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= self.MAX_CONSECUTIVE_EMPTY_PAGES:
                    return summaries
                start += self.PAGE_SIZE
                continue

            consecutive_empty_pages = 0
            for position in positions:
                normalized = dict(position)
                normalized["_board_base_url"] = config["base_url"]
                summaries.append(normalized)

            if total_count is not None and len(summaries) >= total_count:
                return summaries[:total_count]

            start += self.PAGE_SIZE

    async def _fetch_all_details(
        self,
        client: httpx.AsyncClient,
        config: dict[str, str],
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(self.DETAIL_CONCURRENCY)

        async def fetch_detail(summary: dict[str, Any]) -> dict[str, Any]:
            position_id = summary.get("id")
            params = {
                "position_id": position_id,
                "domain": config["domain"],
                "hl": "en",
            }

            async with semaphore:
                try:
                    payload = await self._request_json(
                        client,
                        url=f"{config['base_url']}{self.DETAIL_PATH}",
                        params=params,
                    )
                except Exception:
                    failed_summary = dict(summary)
                    failed_summary["_detail_fetch_failed"] = True
                    return failed_summary

            detail = payload.get("data")
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
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                response = await client.get(url, params=params)
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
                raise ValueError("Eightfold response payload must be a JSON object")
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code
                if (
                    status_code not in self.RETRYABLE_STATUS_CODES
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
        raise RuntimeError("Eightfold request failed without an exception")

    @staticmethod
    def _extract_positions(data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []

        positions = data.get("positions")
        if not isinstance(positions, list):
            return []

        return [position for position in positions if isinstance(position, dict)]

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
