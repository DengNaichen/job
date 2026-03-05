from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class GreenhouseFetcher(BaseFetcher):
    """Greenhouse API fetcher."""

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    @property
    def source_name(self) -> str:
        return "greenhouse"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        """
        Fetch job data from Greenhouse.

        Args:
            slug: Board ID (e.g., 'airbnb')
            include_content: Whether to include job description content

        Returns:
            List of raw job data
        """
        url = f"{self.BASE_URL}/{slug}/jobs"
        params = {"content": str(include_content).lower()}

        async with httpx.AsyncClient() as client:
            data = await self.request_json_with_retry(
                client,
                url=url,
                params=params,
            )

        return data.get("jobs", [])
