from __future__ import annotations

import pytest

from app.models import SyncRunStatus
from app.repositories.sync_run import SyncRunRepository
from app.contracts.sync import SourceSyncStats


@pytest.mark.asyncio
async def test_create_running_and_get_running_by_source(session) -> None:
    repo = SyncRunRepository(session)

    run = await repo.create_running(source="greenhouse:airbnb")
    found = await repo.get_running_by_source(source="greenhouse:airbnb")

    assert run.status == SyncRunStatus.running
    assert run.finished_at is None
    assert run.started_at.tzinfo is None
    assert run.created_at.tzinfo is None
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
    assert finished.finished_at.tzinfo is None
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
    assert run.started_at.tzinfo is None
    assert run.finished_at.tzinfo is None
    assert run.error_summary == "unsupported platform"


@pytest.mark.asyncio
async def test_has_any_for_source(session) -> None:
    repo = SyncRunRepository(session)

    assert await repo.has_any_for_source(source="greenhouse:airbnb") is False

    await repo.create_running(source="greenhouse:airbnb")

    assert await repo.has_any_for_source(source="greenhouse:airbnb") is True


# ------------------------------------------------------------------ #
# Phase 3 — source_id authoritative helpers (T010)                    #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_create_running_dual_writes_source_id(session) -> None:
    """create_running stores source_id when provided (dual-write)."""
    repo = SyncRunRepository(session)

    run = await repo.create_running(source="greenhouse:notion", source_id="src-uuid-001")

    assert run.source == "greenhouse:notion"
    assert run.source_id == "src-uuid-001"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_create_finished_dual_writes_source_id(session) -> None:
    """create_finished stores source_id when provided (dual-write)."""
    from app.models import SyncRunStatus

    repo = SyncRunRepository(session)

    run = await repo.create_finished(
        source="greenhouse:notion",
        source_id="src-uuid-002",
        status=SyncRunStatus.failed,
        error_summary="unsupported",
    )

    assert run.source_id == "src-uuid-002"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_get_running_by_source_id_finds_running_run(session) -> None:
    """get_running_by_source_id returns a running sync run for the given source_id."""
    repo = SyncRunRepository(session)

    run = await repo.create_running(source="greenhouse:linear", source_id="src-uuid-003")
    found = await repo.get_running_by_source_id(source_id="src-uuid-003")

    assert found is not None
    assert found.id == run.id


@pytest.mark.asyncio
async def test_get_running_by_source_id_returns_none_when_finished(session) -> None:
    """get_running_by_source_id returns None once the run is finished."""
    from app.models import SyncRunStatus

    repo = SyncRunRepository(session)

    run = await repo.create_running(source="greenhouse:figma", source_id="src-uuid-004")
    await repo.finish(run=run, status=SyncRunStatus.success)

    found = await repo.get_running_by_source_id(source_id="src-uuid-004")

    assert found is None


@pytest.mark.asyncio
async def test_get_running_by_source_id_returns_none_for_different_source(session) -> None:
    """get_running_by_source_id does not cross source boundaries."""
    repo = SyncRunRepository(session)

    await repo.create_running(source="greenhouse:linear", source_id="src-uuid-005")

    found = await repo.get_running_by_source_id(source_id="src-uuid-999")

    assert found is None


@pytest.mark.asyncio
async def test_has_any_for_source_id_returns_false_when_no_runs(session) -> None:
    repo = SyncRunRepository(session)

    assert await repo.has_any_for_source_id(source_id="src-uuid-100") is False


@pytest.mark.asyncio
async def test_has_any_for_source_id_returns_true_after_run_created(session) -> None:
    repo = SyncRunRepository(session)

    assert await repo.has_any_for_source_id(source_id="src-uuid-101") is False

    await repo.create_running(source="greenhouse:rippling", source_id="src-uuid-101")

    assert await repo.has_any_for_source_id(source_id="src-uuid-101") is True
