"""SyncRun repository for database operations."""

from datetime import datetime, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import SyncRun, SyncRunStatus
from app.services.full_snapshot_sync import SourceSyncStats


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _apply_stats(run: SyncRun, stats: SourceSyncStats | None) -> None:
    if stats is None:
        return
    run.fetched_count = stats.fetched_count
    run.mapped_count = stats.mapped_count
    run.unique_count = stats.unique_count
    run.deduped_by_external_id = stats.deduped_by_external_id
    run.inserted_count = stats.inserted_count
    run.updated_count = stats.updated_count
    run.closed_count = stats.closed_count
    run.failed_count = stats.failed_count


class SyncRunRepository:
    """Repository for SyncRun database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_running(self, *, source: str) -> SyncRun:
        run = SyncRun(
            source=source,
            status=SyncRunStatus.running,
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def create_finished(
        self,
        *,
        source: str,
        status: SyncRunStatus,
        error_summary: str | None = None,
        stats: SourceSyncStats | None = None,
    ) -> SyncRun:
        run = SyncRun(
            source=source,
            status=status,
            finished_at=_now_utc(),
            error_summary=error_summary,
        )
        _apply_stats(run, stats)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_running_by_source(self, *, source: str) -> SyncRun | None:
        result = await self.session.exec(
            select(SyncRun)
            .where(
                SyncRun.source == source,
                SyncRun.status == SyncRunStatus.running,
            )
            .order_by(SyncRun.started_at.desc())
        )
        return result.first()

    async def finish(
        self,
        *,
        run: SyncRun,
        status: SyncRunStatus,
        error_summary: str | None = None,
        stats: SourceSyncStats | None = None,
    ) -> SyncRun:
        run.status = status
        run.finished_at = _now_utc()
        run.error_summary = error_summary
        _apply_stats(run, stats)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def has_any_for_source(self, *, source: str) -> bool:
        result = await self.session.exec(
            select(SyncRun.id)
            .where(SyncRun.source == source)
            .limit(1)
        )
        return result.first() is not None
