from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlmodel import SQLModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import PlatformType, Source, SyncRun, SyncRunStatus, build_source_key
from app.repositories.sync_run import SyncRunRepository
from app.services.application.full_snapshot_sync import SourceSyncResult, SourceSyncStats
from app.services.application.sync import SyncService


def _make_source(identifier: str, platform: PlatformType = PlatformType.GREENHOUSE) -> Source:
    return Source(
        name=identifier.title(),
        name_normalized=identifier,
        platform=platform,
        identifier=identifier,
    )


async def _list_sync_runs(test_engine) -> Sequence[SyncRun]:
    async with AsyncSession(test_engine) as session:
        result = await session.exec(select(SyncRun).order_by(SyncRun.created_at))
        return list(result.all())


async def _init_tables(test_engine) -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


@pytest.mark.asyncio
async def test_sync_service_success_records_successful_run(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        source = _make_source("airbnb")

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=True,
                stats=SourceSyncStats(
                    fetched_count=4,
                    mapped_count=4,
                    unique_count=3,
                    deduped_by_external_id=1,
                    inserted_count=2,
                    updated_count=1,
                    closed_count=1,
                ),
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(
            source=source, include_content=True, dry_run=False, retry_attempts=1
        )

        assert sync_run.status == SyncRunStatus.success
        assert sync_run.fetched_count == 4
        assert sync_run.closed_count == 1

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.success
        # Phase 3: sync_run should be created with source_id
        assert rows[0].source_id == str(source.id)  # type: ignore[attr-defined]
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_sync_service_retries_once_then_succeeds(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        source = _make_source("stripe")
        calls = {"count": 0}

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            calls["count"] += 1
            if calls["count"] == 1:
                return SourceSyncResult(
                    source_id=str(source.id),
                    source_key=build_source_key(source.platform, source.identifier),
                    ok=False,
                    stats=SourceSyncStats(fetched_count=2, failed_count=2),
                    error="temporary failure",
                )
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=True,
                stats=SourceSyncStats(
                    fetched_count=3,
                    mapped_count=3,
                    unique_count=3,
                    inserted_count=2,
                    updated_count=1,
                ),
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=2)

        assert calls["count"] == 2
        assert sync_run.status == SyncRunStatus.success
        assert sync_run.fetched_count == 3

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.success
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_sync_service_marks_failed_after_retry_exhausted(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        source = _make_source("openai")

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            return SourceSyncResult(
                source_id=str(source.id),
                source_key=build_source_key(source.platform, source.identifier),
                ok=False,
                stats=SourceSyncStats(fetched_count=1, failed_count=1),
                error="permanent failure",
            )

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert sync_run.status == SyncRunStatus.failed
        assert sync_run.error_summary == "permanent failure"

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.failed
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_sync_service_skips_overlap_without_running_snapshot(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _init_tables(test_engine)
    try:
        source = _make_source("notion")
        service = SyncService(engine=test_engine)

        async with AsyncSession(test_engine) as session:
            repo = SyncRunRepository(session)
            # Seed with source_id so the authoritative overlap check finds it
            await repo.create_running(
                source_id=str(source.id),
            )

        called = {"value": False}

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            called["value"] = True
            raise AssertionError("should not be called")

        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert called["value"] is False
        assert sync_run.status == SyncRunStatus.failed
        assert sync_run.error_summary == "overlap: source already running"

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 2
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_sync_service_handles_running_conflict_during_create(
    test_engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _init_tables(test_engine)
    try:
        source = _make_source("figma")
        service = SyncService(engine=test_engine)

        async def fake_try_create_running(self, *, source_id: str | None = None):  # noqa: ANN001
            _ = (self, source_id)
            return None

        called = {"value": False}

        async def fake_execute_snapshot_sync(**kwargs):  # noqa: ANN001
            _ = kwargs
            called["value"] = True
            raise AssertionError("should not be called")

        monkeypatch.setattr(SyncRunRepository, "try_create_running", fake_try_create_running)
        monkeypatch.setattr(service, "_execute_snapshot_sync", fake_execute_snapshot_sync)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert called["value"] is False
        assert sync_run.status == SyncRunStatus.failed
        assert sync_run.error_summary == "overlap: source already running"

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
    finally:
        await test_engine.dispose()


@pytest.mark.asyncio
async def test_sync_service_marks_unsupported_platform_failed(test_engine) -> None:
    await _init_tables(test_engine)
    try:
        service = SyncService(engine=test_engine)
        source = _make_source("acme", platform=PlatformType.WORKDAY)

        sync_run = await service.sync_source(source=source, retry_attempts=1)

        assert sync_run.status == SyncRunStatus.failed
        assert sync_run.error_summary == "unsupported platform: workday"

        rows = await _list_sync_runs(test_engine)
        assert len(rows) == 1
        assert rows[0].status == SyncRunStatus.failed
    finally:
        await test_engine.dispose()
