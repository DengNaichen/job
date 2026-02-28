from __future__ import annotations

import pytest

from app.models import SyncRunStatus
from app.repositories.sync_run import SyncRunRepository
from app.services.full_snapshot_sync import SourceSyncStats


@pytest.mark.asyncio
async def test_create_running_and_get_running_by_source(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_running(source="greenhouse:airbnb")
    found = await repo.get_running_by_source(source="greenhouse:airbnb")

    assert run.status == SyncRunStatus.running
    assert run.finished_at is None
    assert found is not None
    assert found.id == run.id


@pytest.mark.asyncio
async def test_finish_updates_stats_and_error_summary(session) -> None:
    repo = SyncRunRepository(session)
    run = await repo.create_running(source="greenhouse:airbnb")

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
    assert finished.error_summary == "fetch boom"
    assert finished.fetched_count == 5
    assert finished.deduped_by_external_id == 1
    assert finished.failed_count == 4


@pytest.mark.asyncio
async def test_create_finished_creates_terminal_run(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_finished(
        source="apple:apple",
        status=SyncRunStatus.failed,
        error_summary="unsupported platform",
    )

    assert run.status == SyncRunStatus.failed
    assert run.finished_at is not None
    assert run.error_summary == "unsupported platform"


@pytest.mark.asyncio
async def test_has_any_for_source(session) -> None:
    repo = SyncRunRepository(session)

    assert await repo.has_any_for_source(source="greenhouse:airbnb") is False

    await repo.create_running(source="greenhouse:airbnb")

    assert await repo.has_any_for_source(source="greenhouse:airbnb") is True
