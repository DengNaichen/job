from __future__ import annotations

import pytest

from app.models import SyncRunStatus, build_source_key
from app.services.application.full_snapshot_sync import SourceSyncResult, SourceSyncStats
from app.services.application.sync import SyncService


@pytest.mark.asyncio
async def test_snapshot_refresh_contract_triggers_after_successful_snapshot(
    test_engine,
    init_sync_tables,
    list_sync_runs,
    source_factory,
    make_embedding_refresh_stub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_sync_tables(test_engine)
    try:
        source = source_factory("contract-success")
        refresh_stub = make_embedding_refresh_stub()
        service = SyncService(
            engine=test_engine,
            embedding_refresh_factory=lambda _session: refresh_stub,
        )

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=True,
                stats=SourceSyncStats(fetched_count=2, unique_count=2),
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)
        rows = await list_sync_runs(test_engine)

        assert sync_run.status == SyncRunStatus.success
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.success
        assert refresh_stub.calls == [
            {
                "source_id": str(source.id),
                "snapshot_run_id": str(sync_run.id),
            }
        ]
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_refresh_contract_does_not_trigger_after_failed_snapshot(
    test_engine,
    init_sync_tables,
    source_factory,
    make_embedding_refresh_stub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_sync_tables(test_engine)
    try:
        source = source_factory("contract-failed")
        refresh_stub = make_embedding_refresh_stub()
        service = SyncService(
            engine=test_engine,
            embedding_refresh_factory=lambda _session: refresh_stub,
        )

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=False,
                stats=SourceSyncStats(fetched_count=1, failed_count=1),
                error="sync failed",
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert sync_run.status == SyncRunStatus.failed
        assert refresh_stub.calls == []
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_refresh_contract_dry_run_does_not_trigger_refresh(
    test_engine,
    init_sync_tables,
    source_factory,
    make_embedding_refresh_stub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await init_sync_tables(test_engine)
    try:
        source = source_factory("contract-dry-run")
        refresh_stub = make_embedding_refresh_stub()
        service = SyncService(
            engine=test_engine,
            embedding_refresh_factory=lambda _session: refresh_stub,
        )

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=True,
                stats=SourceSyncStats(fetched_count=1, unique_count=1),
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1, dry_run=True)

        assert sync_run.status == SyncRunStatus.success
        assert refresh_stub.calls == []
    finally:
        await test_engine.dispose()
