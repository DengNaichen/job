from abc import ABC, abstractmethod
import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class RetryConfig:
    """Configuration for HTTP retry behavior."""

    max_retries: int = 3
    retryable_status_codes: set[int] = field(
        default_factory=lambda: {429, 500, 502, 503, 504}
    )
    backoff_base_seconds: float = 0.25
    exponential_backoff: bool = True


class BaseFetcher(ABC):
    """Base class for data source fetchers."""

    # Default retry configuration - subclasses can override
    retry_config: RetryConfig = RetryConfig()

    # Set to False to disable retry entirely
    retry_enabled: bool = True

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

    async def request_with_retry(
        self,
        client: httpx.AsyncClient,
        *,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """
        Execute an HTTP request with retry logic.

        Retries on:
        - httpx.RequestError (network/connection errors)
        - HTTP status codes in retry_config.retryable_status_codes

        Uses exponential backoff: backoff_base_seconds * (2 ** attempt)
        (or fixed delay if exponential_backoff is False)

        Raises:
            httpx.HTTPStatusError: For non-retryable HTTP errors or after max retries
            httpx.RequestError: For network errors after max retries
        """
        if not self.retry_enabled:
            response = await client.request(
                method, url, params=params, json=json, headers=headers
            )
            response.raise_for_status()
            return response

        last_error: Exception | None = None
        config = self.retry_config

        for attempt in range(config.max_retries):
            try:
                response = await client.request(
                    method, url, params=params, json=json, headers=headers
                )
                if response.status_code in config.retryable_status_codes:
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
                    exc.response.status_code not in config.retryable_status_codes
                    or attempt + 1 >= config.max_retries
                ):
                    raise
            except httpx.RequestError as exc:
                last_error = exc
                if attempt + 1 >= config.max_retries:
                    raise

            if config.exponential_backoff:
                await asyncio.sleep(config.backoff_base_seconds * (2**attempt))
            else:
                await asyncio.sleep(config.backoff_base_seconds)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"{self.source_name} request failed without an exception")

    async def request_json_with_retry(
        self,
        client: httpx.AsyncClient,
        *,
        method: str = "GET",
        url: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute an HTTP request and parse JSON response with retry logic.

        Raises:
            ValueError: If response is not a JSON object
            httpx.HTTPStatusError: For HTTP errors after retries exhausted
            httpx.RequestError: For network errors after retries exhausted
        """
        response = await self.request_with_retry(
            client, method=method, url=url, params=params, json=json, headers=headers
        )
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        raise ValueError(f"{self.source_name} response payload must be a JSON object")

    async def request_with_graceful_retry(
        self,
        client: httpx.AsyncClient,
        *,
        url: str,
        params: dict[str, Any] | None = None,
        retry_config: RetryConfig | None = None,
    ) -> httpx.Response | None:
        """
        Execute an HTTP GET request with retry and graceful failure handling.

        Used by fetchers that want:
        - Retry on server errors
        - Return None on failure instead of raising
        - Special handling for 404 (returns None, not an error)

        Args:
            client: HTTP client
            url: Request URL
            params: Query parameters
            retry_config: Optional custom retry config (uses self.retry_config if None)

        Returns:
            Response on success, None on failure or 404
        """
        config = retry_config or self.retry_config

        for attempt in range(config.max_retries):
            try:
                response = await client.get(url, params=params)

                # 404 is terminal but not an error for this pattern
                if response.status_code == 404:
                    return None

                # Retryable server errors
                if response.status_code in config.retryable_status_codes:
                    if attempt + 1 < config.max_retries:
                        if config.exponential_backoff:
                            await asyncio.sleep(config.backoff_base_seconds * (2**attempt))
                        else:
                            await asyncio.sleep(config.backoff_base_seconds)
                        continue
                    return None

                # Non-retryable client errors
                if response.status_code >= 400:
                    return None

                return response

            except httpx.RequestError:
                if attempt + 1 >= config.max_retries:
                    return None
                if config.exponential_backoff:
                    await asyncio.sleep(config.backoff_base_seconds * (2**attempt))
                else:
                    await asyncio.sleep(config.backoff_base_seconds)

        return None

    @staticmethod
    def _to_int_or_none(value: Any) -> int | None:
        """Safely convert a value to int, returning None on failure."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
