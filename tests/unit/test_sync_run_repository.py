from __future__ import annotations

import pytest

from app.contracts.sync import SourceSyncStats
from app.models import SyncRunStatus
from app.repositories.sync_run import SyncRunRepository


@pytest.mark.asyncio
async def test_create_running_and_get_running_by_source_id(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_running(source_id="src-uuid-001")
    found = await repo.get_running_by_source_id(source_id="src-uuid-001")

    assert run.source_id == "src-uuid-001"
    assert run.status == SyncRunStatus.running
    assert run.finished_at is None
    assert run.started_at.tzinfo is None
    assert run.created_at.tzinfo is None
    assert found is not None
    assert found.id == run.id


@pytest.mark.asyncio
async def test_finish_updates_stats_and_error_summary(session) -> None:
    repo = SyncRunRepository(session)
    run = await repo.create_running(source_id="src-uuid-002")

    finished = await repo.finish(
        run=run,
        status=SyncRunStatus.failed,
        error_summary="fetch boom",
        stats=SourceSyncStats(
            fetched_count=5,
            mapped_count=4,
            unique_count=4,
            deduped_by_external_id=1,
            inserted_count=2,
            updated_count=1,
            closed_count=1,
            failed_count=4,
        ),
    )

    assert finished.status == SyncRunStatus.failed
    assert finished.finished_at is not None
    assert finished.finished_at.tzinfo is None
    assert finished.error_summary == "fetch boom"
    assert finished.fetched_count == 5
    assert finished.deduped_by_external_id == 1
    assert finished.failed_count == 4


@pytest.mark.asyncio
async def test_create_finished_creates_terminal_run(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_finished(
        source_id="src-uuid-003",
        status=SyncRunStatus.failed,
        error_summary="unsupported platform",
    )

    assert run.source_id == "src-uuid-003"
    assert run.status == SyncRunStatus.failed
    assert run.finished_at is not None
    assert run.started_at.tzinfo is None
    assert run.finished_at.tzinfo is None
    assert run.error_summary == "unsupported platform"


@pytest.mark.asyncio
async def test_get_running_by_source_id_returns_none_when_finished(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_running(source_id="src-uuid-004")
    await repo.finish(run=run, status=SyncRunStatus.success)

    found = await repo.get_running_by_source_id(source_id="src-uuid-004")
    assert found is None


@pytest.mark.asyncio
async def test_has_any_for_source_id(session) -> None:
    repo = SyncRunRepository(session)

    assert await repo.has_any_for_source_id(source_id="src-uuid-005") is False
    await repo.create_running(source_id="src-uuid-005")
    assert await repo.has_any_for_source_id(source_id="src-uuid-005") is True
