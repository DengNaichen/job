import pytest
import respx
from httpx import AsyncClient, Response

from app.ingest.fetchers.base import BaseFetcher, RetryConfig


class ConcreteFetcher(BaseFetcher):
    """Concrete implementation for testing."""

    @property
    def source_name(self) -> str:
        return "test"

    async def fetch(self, slug: str, **kwargs) -> list[dict]:
        return []


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_default_values(self) -> None:
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.retryable_status_codes == {429, 500, 502, 503, 504}
        assert config.backoff_base_seconds == 0.25
        assert config.exponential_backoff is True

    def test_custom_values(self) -> None:
        config = RetryConfig(
            max_retries=5,
            retryable_status_codes={500, 502},
            backoff_base_seconds=0.5,
            exponential_backoff=False,
        )
        assert config.max_retries == 5
        assert config.retryable_status_codes == {500, 502}
        assert config.backoff_base_seconds == 0.5
        assert config.exponential_backoff is False


class TestBaseFetcherRetry:
    """Tests for BaseFetcher retry logic."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_500_error(self) -> None:
        """Should retry on 500 status code."""
        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(500, json={"error": "server error"}),
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()
        async with AsyncClient() as client:
            response = await fetcher.request_with_retry(
                client, method="GET", url="https://example.com/api"
            )

        assert response.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_429_rate_limit(self) -> None:
        """Should retry on 429 status code."""
        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(429, json={"error": "rate limited"}),
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()
        async with AsyncClient() as client:
            response = await fetcher.request_with_retry(
                client, method="GET", url="https://example.com/api"
            )

        assert response.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_on_502_503_504(self) -> None:
        """Should retry on 502, 503, 504 status codes."""
        for status_code in [502, 503, 504]:
            respx.clear()
            route = respx.get("https://example.com/api").mock(
                side_effect=[
                    Response(status_code, json={"error": "bad gateway"}),
                    Response(200, json={"data": "success"}),
                ]
            )

            fetcher = ConcreteFetcher()
            async with AsyncClient() as client:
                response = await fetcher.request_with_retry(
                    client, method="GET", url="https://example.com/api"
                )

            assert response.status_code == 200
            assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_raises_after_max_retries_exhausted(self) -> None:
        """Should raise HTTPStatusError after max retries exhausted."""
        respx.get("https://example.com/api").mock(
            return_value=Response(500, json={"error": "server error"})
        )

        fetcher = ConcreteFetcher()
        fetcher.retry_config = RetryConfig(max_retries=2)

        async with AsyncClient() as client:
            with pytest.raises(Exception):  # HTTPStatusError
                await fetcher.request_with_retry(
                    client, method="GET", url="https://example.com/api"
                )

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_retry_when_disabled(self) -> None:
        """Should not retry when retry_enabled is False."""
        route = respx.get("https://example.com/api").mock(
            return_value=Response(500, json={"error": "server error"})
        )

        fetcher = ConcreteFetcher()
        fetcher.retry_enabled = False

        async with AsyncClient() as client:
            with pytest.raises(Exception):
                await fetcher.request_with_retry(
                    client, method="GET", url="https://example.com/api"
                )

        assert route.call_count == 1  # No retry

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_retry_on_4xx_client_errors(self) -> None:
        """Should not retry on 4xx client errors (except 429)."""
        route = respx.get("https://example.com/api").mock(
            return_value=Response(404, json={"error": "not found"})
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            with pytest.raises(Exception):  # HTTPStatusError
                await fetcher.request_with_retry(
                    client, method="GET", url="https://example.com/api"
                )

        assert route.call_count == 1  # No retry

    @pytest.mark.asyncio
    @respx.mock
    async def test_custom_retryable_codes(self) -> None:
        """Should respect custom retryable status codes."""
        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(418, json={"error": "I'm a teapot"}),  # Custom code
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()
        fetcher.retry_config = RetryConfig(retryable_status_codes={418, 500, 502, 503, 504})

        async with AsyncClient() as client:
            response = await fetcher.request_with_retry(
                client, method="GET", url="https://example.com/api"
            )

        assert response.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_request_json_with_retry_parses_json(self) -> None:
        """Should parse JSON response."""
        respx.get("https://example.com/api").mock(
            return_value=Response(200, json={"data": "success"})
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            payload = await fetcher.request_json_with_retry(client, url="https://example.com/api")

        assert payload == {"data": "success"}

    @pytest.mark.asyncio
    @respx.mock
    async def test_request_json_with_retry_raises_on_non_object(self) -> None:
        """Should raise ValueError if response is not a JSON object."""
        respx.get("https://example.com/api").mock(
            return_value=Response(200, json=["not", "an", "object"])
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            with pytest.raises(ValueError, match="must be a JSON object"):
                await fetcher.request_json_with_retry(client, url="https://example.com/api")


class TestGracefulRetry:
    """Tests for request_with_graceful_retry method."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_none_on_404(self) -> None:
        """Should return None on 404."""
        respx.get("https://example.com/api").mock(
            return_value=Response(404, json={"error": "not found"})
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api"
            )

        assert result is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_none_on_server_error_after_retries(self) -> None:
        """Should return None after server errors exhaust retries."""
        respx.get("https://example.com/api").mock(
            return_value=Response(500, json={"error": "server error"})
        )

        fetcher = ConcreteFetcher()
        fetcher.retry_config = RetryConfig(max_retries=2)

        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api"
            )

        assert result is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_retries_and_succeeds(self) -> None:
        """Should retry and succeed on second attempt."""
        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(500, json={"error": "server error"}),
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api"
            )

        assert result is not None
        assert result.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_uses_custom_retry_config(self) -> None:
        """Should use custom retry config when provided."""
        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(418, json={"error": "teapot"}),  # Custom code
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()
        custom_config = RetryConfig(
            max_retries=2,
            retryable_status_codes={418},
        )

        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api", retry_config=custom_config
            )

        assert result is not None
        assert result.status_code == 200
        assert route.call_count == 2

    @pytest.mark.asyncio
    @respx.mock
    async def test_returns_none_on_4xx_client_errors(self) -> None:
        """Should return None on 4xx client errors (except 404 which is handled above)."""
        respx.get("https://example.com/api").mock(
            return_value=Response(403, json={"error": "forbidden"})
        )

        fetcher = ConcreteFetcher()

        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api"
            )

        assert result is None

    @pytest.mark.asyncio
    @respx.mock
    async def test_fixed_backoff_when_exponential_disabled(self) -> None:
        """Should use fixed backoff when exponential_backoff is False."""
        import time

        route = respx.get("https://example.com/api").mock(
            side_effect=[
                Response(500, json={"error": "error 1"}),
                Response(500, json={"error": "error 2"}),
                Response(200, json={"data": "success"}),
            ]
        )

        fetcher = ConcreteFetcher()
        fetcher.retry_config = RetryConfig(
            max_retries=3,
            backoff_base_seconds=0.05,  # Fast for testing
            exponential_backoff=False,
        )

        start = time.monotonic()
        async with AsyncClient() as client:
            result = await fetcher.request_with_graceful_retry(
                client, url="https://example.com/api"
            )
        elapsed = time.monotonic() - start

        assert result is not None
        # With fixed backoff 0.05: sleep 0.05 + 0.05 = 0.10 minimum
        assert elapsed >= 0.10
        assert route.call_count == 3
