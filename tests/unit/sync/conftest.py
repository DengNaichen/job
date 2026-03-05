from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlatformType, Source, SyncRun
from app.services.application.embedding_refresh import EmbeddingRefreshExecutionResult


def _make_source(
    identifier: str,
    platform: PlatformType = PlatformType.GREENHOUSE,
) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=platform,
        identifier=identifier,
    )


@pytest.fixture
def source_factory():
    return _make_source


@pytest.fixture
def init_sync_tables():
    async def _init(test_engine) -> None:  # noqa: ANN001
        async with test_engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    return _init


@pytest.fixture
def list_sync_runs():
    async def _list(test_engine) -> Sequence[SyncRun]:  # noqa: ANN001
        async with AsyncSession(test_engine) as session:
            result = await session.exec(select(SyncRun).order_by(SyncRun.created_at))
            return list(result.all())

    return _list


@pytest.fixture
def make_embedding_refresh_stub():
    class _StubEmbeddingRefreshService:
        def __init__(
            self,
            *,
            result: EmbeddingRefreshExecutionResult | None = None,
            error: Exception | None = None,
        ) -> None:
            self.result = result or EmbeddingRefreshExecutionResult(
                source_id="",
                snapshot_run_id=None,
                triggered=True,
            )
            self.error = error
            self.calls: list[dict[str, str | None]] = []

        async def refresh_for_source(
            self,
            *,
            source_id: str,
            snapshot_run_id: str | None = None,
        ) -> EmbeddingRefreshExecutionResult:
            self.calls.append(
                {
                    "source_id": source_id,
                    "snapshot_run_id": snapshot_run_id,
                }
            )
            if self.error is not None:
                raise self.error
            return EmbeddingRefreshExecutionResult(
                source_id=source_id,
                snapshot_run_id=snapshot_run_id,
                triggered=self.result.triggered,
                selected_jobs=self.result.selected_jobs,
                attempted_jobs=self.result.attempted_jobs,
                refreshed_jobs=self.result.refreshed_jobs,
                failed_jobs=self.result.failed_jobs,
                skipped_jobs=self.result.skipped_jobs,
                error=self.result.error,
            )

    return _StubEmbeddingRefreshService
