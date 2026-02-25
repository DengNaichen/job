from abc import ABC, abstractmethod
from typing import Any


class BaseFetcher(ABC):
    """Base class for data source fetchers."""

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Data source name."""
        pass

    @abstractmethod
    async def fetch(self, slug: str, **kwargs) -> list[dict[str, Any]]:
        """
        Fetch job data from data source.

        Args:
            slug: Data source identifier (e.g., company name, board ID)
            **kwargs: Additional parameters

        Returns:
            List of raw job data
        """
        pass
