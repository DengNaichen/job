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
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        return data.get("jobs", [])
