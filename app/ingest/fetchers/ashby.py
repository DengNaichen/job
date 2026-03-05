from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class AshbyFetcher(BaseFetcher):
    """Ashby public job board fetcher."""

    BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"

    @property
    def source_name(self) -> str:
        return "ashby"

    async def fetch(
        self,
        slug: str,
        include_content: bool = False,
        include_compensation: bool | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetch job data from an Ashby public job board.

        FullSnapshotSyncService exposes a generic include_content flag.
        For Ashby, that flag is reused to request optional compensation data.
        """
        include_compensation_flag = (
            include_content if include_compensation is None else include_compensation
        )
        url = f"{self.BASE_URL}/{slug}"
        params = {"includeCompensation": str(include_compensation_flag).lower()}

        async with httpx.AsyncClient() as client:
            data = await self.request_json_with_retry(
                client,
                url=url,
                params=params,
            )

        jobs = data.get("jobs", [])
        return jobs if isinstance(jobs, list) else []
