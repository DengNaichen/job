import asyncio
from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class SmartRecruitersFetcher(BaseFetcher):
    """SmartRecruiters public postings fetcher."""

    BASE_URL = "https://api.smartrecruiters.com/v1/companies"
    PAGE_SIZE = 100
    REQUEST_TIMEOUT_SECONDS = 60.0
    DETAIL_CONCURRENCY = 8
    DETAIL_RETRY_ATTEMPTS = 2
    DETAIL_RETRY_DELAY_SECONDS = 0.25

    @property
    def source_name(self) -> str:
        return "smartrecruiters"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        """
        Fetch job data from a SmartRecruiters company board.

        The public list endpoint is paginated and omits fields required by the
        ingest schema, including applyUrl and full jobAd sections. For that
        reason, the detail endpoint is fetched for every posting regardless of
        include_content.
        """
        _ = include_content

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS)) as client:
            summaries = await self._fetch_all_summaries(client, slug)
            if not summaries:
                return []
            return await self._fetch_all_details(client, slug, summaries)

    async def _fetch_all_summaries(self, client: httpx.AsyncClient, slug: str) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        offset = 0

        while True:
            url = f"{self.BASE_URL}/{slug}/postings"
            params = {"limit": self.PAGE_SIZE, "offset": offset}

            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            content = data.get("content", [])
            if not isinstance(content, list):
                return summaries

            summaries.extend(item for item in content if isinstance(item, dict))

            if not content:
                return summaries

            total_found = self._to_int_or_none(data.get("totalFound"))
            current_offset = self._to_int_or_none(data.get("offset")) or offset
            page_limit = self._to_int_or_none(data.get("limit")) or self.PAGE_SIZE
            next_offset = current_offset + len(content)

            if total_found is not None and next_offset >= total_found:
                return summaries
            if len(content) < page_limit:
                return summaries

            offset = next_offset

    async def _fetch_all_details(
        self,
        client: httpx.AsyncClient,
        slug: str,
        summaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        semaphore = asyncio.Semaphore(self.DETAIL_CONCURRENCY)

        async def fetch_detail(summary: dict[str, Any]) -> dict[str, Any] | None:
            detail_url = self._detail_url(summary, slug)
            async with semaphore:
                for attempt in range(self.DETAIL_RETRY_ATTEMPTS):
                    try:
                        response = await client.get(detail_url)
                    except httpx.RequestError:
                        if attempt + 1 < self.DETAIL_RETRY_ATTEMPTS:
                            await asyncio.sleep(self.DETAIL_RETRY_DELAY_SECONDS)
                            continue
                        return None

                    if response.status_code == 404:
                        return None

                    if response.status_code in {500, 502, 503, 504}:
                        if attempt + 1 < self.DETAIL_RETRY_ATTEMPTS:
                            await asyncio.sleep(self.DETAIL_RETRY_DELAY_SECONDS)
                            continue
                        return None

                    response.raise_for_status()
                    detail = response.json()
                    if not isinstance(detail, dict):
                        return None

                    merged = dict(summary)
                    merged.update(detail)
                    return merged

            return None

        details = await asyncio.gather(*(fetch_detail(summary) for summary in summaries))
        return [detail for detail in details if detail is not None]

    @staticmethod
    def _detail_url(summary: dict[str, Any], slug: str) -> str:
        ref = summary.get("ref")
        if isinstance(ref, str) and ref.strip():
            return ref.strip()
        posting_id = str(summary.get("id", "")).strip()
        return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{posting_id}"

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
