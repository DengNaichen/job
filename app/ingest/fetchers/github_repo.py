from typing import Any

import httpx

from app.ingest.fetchers.base import BaseFetcher


class GitHubRepoFetcher(BaseFetcher):
    """Fetch jobs from a JSON file in a public GitHub repository."""

    RAW_BASE_URL = "https://raw.githubusercontent.com"

    @property
    def source_name(self) -> str:
        return "github"

    async def fetch(self, slug: str, ref: str = "main") -> list[dict[str, Any]]:
        """
        Fetch raw jobs from GitHub JSON.

        slug format:
            owner/repo:path/to/jobs.json
        """
        owner_repo, path = self._parse_slug(slug)
        url = f"{self.RAW_BASE_URL}/{owner_repo}/{ref}/{path}"

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "job-service-ingest/0.1"},
            )
            response.raise_for_status()
            payload = response.json()

        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            jobs = payload.get("jobs", [])
            if isinstance(jobs, list):
                return [item for item in jobs if isinstance(item, dict)]
        return []

    @staticmethod
    def _parse_slug(slug: str) -> tuple[str, str]:
        if ":" not in slug:
            raise ValueError(
                "Invalid github identifier. Expected format: owner/repo:path/to/jobs.json"
            )
        owner_repo, path = slug.split(":", 1)
        owner_repo = owner_repo.strip()
        path = path.strip().lstrip("/")

        if owner_repo.count("/") != 1 or not path:
            raise ValueError(
                "Invalid github identifier. Expected format: owner/repo:path/to/jobs.json"
            )
        return owner_repo, path
