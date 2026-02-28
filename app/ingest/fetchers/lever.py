from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class LeverFetcher(BaseFetcher):
    """Lever postings API fetcher."""

    BASE_URL = "https://api.lever.co/v0/postings"
    REQUEST_TIMEOUT_SECONDS = 60.0

    @property
    def source_name(self) -> str:
        return "lever"

    async def fetch(self, slug: str, include_content: bool = True) -> list[dict[str, Any]]:
        """
        Fetch job data from a Lever postings board.

        Lever's public postings endpoint returns a JSON array when mode=json.
        The include_content flag is accepted for fetcher parity but not used by Lever.
        """
        _ = include_content
        url = f"{self.BASE_URL}/{slug}"
        params = {"mode": "json"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(self.REQUEST_TIMEOUT_SECONDS)) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        return data if isinstance(data, list) else []
