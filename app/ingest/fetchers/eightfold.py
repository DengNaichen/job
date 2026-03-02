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
            payload = await self.request_json_with_retry(
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
        async def fetch_detail(
            client: httpx.AsyncClient, summary: dict[str, Any]
        ) -> dict[str, Any] | None:
            position_id = summary.get("id")
            params = {
                "position_id": position_id,
                "domain": config["domain"],
                "hl": "en",
            }

            try:
                payload = await self.request_json_with_retry(
                    client,
                    url=f"{config['base_url']}{self.DETAIL_PATH}",
                    params=params,
                )
            except Exception:
                return None

            detail = payload.get("data")
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

    @staticmethod
    def _extract_positions(data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []

        positions = data.get("positions")
        if not isinstance(positions, list):
            return []

        return [position for position in positions if isinstance(position, dict)]
