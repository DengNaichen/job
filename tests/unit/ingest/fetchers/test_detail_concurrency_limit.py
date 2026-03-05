from __future__ import annotations

import asyncio

import httpx
import pytest

from app.ingest.fetchers import AppleFetcher, EightfoldFetcher, SmartRecruitersFetcher
from app.ingest.fetchers.base import BaseFetcher


class _DummyFetcher(BaseFetcher):
    @property
    def source_name(self) -> str:
        return "dummy"

    async def fetch(self, slug: str, **kwargs) -> list[dict[str, object]]:
        _ = (slug, kwargs)
        return []


class _InFlightTracker:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.in_flight = 0
        self.max_in_flight = 0

    async def enter(self) -> None:
        async with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)

    async def exit(self) -> None:
        async with self._lock:
            self.in_flight -= 1


@pytest.mark.parametrize(
    "fetcher_cls",
    [AppleFetcher, EightfoldFetcher, SmartRecruitersFetcher],
)
def test_summary_detail_fetchers_default_concurrency_is_six(fetcher_cls: type[BaseFetcher]) -> None:
    assert getattr(fetcher_cls, "DETAIL_CONCURRENCY") == 6


@pytest.mark.asyncio
async def test_fetch_details_concurrently_respects_semaphore_limit() -> None:
    fetcher = _DummyFetcher()
    tracker = _InFlightTracker()
    summaries = [{"id": idx} for idx in range(18)]

    async def fetch_detail(client: httpx.AsyncClient, summary: dict[str, object]) -> dict[str, object]:
        _ = client
        await tracker.enter()
        try:
            await asyncio.sleep(0.01)
            return {"id": summary["id"], "ok": True}
        finally:
            await tracker.exit()

    async with httpx.AsyncClient() as client:
        results = await fetcher.fetch_details_concurrently(
            client,
            summaries,
            fetch_detail=fetch_detail,
            concurrency=3,
        )

    assert len(results) == len(summaries)
    assert tracker.max_in_flight <= 3
