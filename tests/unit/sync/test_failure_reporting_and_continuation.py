from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import SyncRun, SyncRunStatus, build_source_key
from app.services.application.full_snapshot_sync import SourceSyncResult, SourceSyncStats
from app.services.application.sync import SyncService


async def _init_tables(test_engine) -> None:  # noqa: ANN001
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def _list_sync_runs(test_engine) -> Sequence[SyncRun]:  # noqa: ANN001
    async with AsyncSession(test_engine) as session:
        result = await session.exec(select(SyncRun).order_by(SyncRun.created_at))
        return list(result.all())


@pytest.mark.asyncio
async def test_retry_exhaustion_marks_source_failed_with_error_details(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
    source_factory,
) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        source = source_factory("failing")

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=False,
                stats=SourceSyncStats(fetched_count=1, failed_count=1),
                error="retry exhausted",
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert sync_run.status == SyncRunStatus.failed
        assert sync_run.error_summary == "retry exhausted"

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.failed
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_next_source_can_run_after_previous_source_failure(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
    source_factory,
) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        first_source = source_factory("failed-source")
        second_source = source_factory("ok-source")

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            source = kwargs["source"]
            if source.identifier == "failed-source":
                return SourceSyncResult(
                    source_id=str(source.id),
                    source_key=build_source_key(source.platform, source.identifier),
                    ok=False,
                    stats=SourceSyncStats(fetched_count=1, failed_count=1),
                    error="upstream transient errors exhausted",
                )
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=True,
                stats=SourceSyncStats(fetched_count=2, unique_count=2),
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        failed_run = await service.sync_source(source=first_source, retry_attempts=1)
        ok_run = await service.sync_source(source=second_source, retry_attempts=1)

        assert failed_run.status == SyncRunStatus.failed
        assert ok_run.status == SyncRunStatus.success

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 2
        assert [row.status for row in rows] == [SyncRunStatus.failed, SyncRunStatus.success]
    finally:
        await test_engine.dispose()
