"""SyncRun repository for database operations."""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.contracts.sync import SourceSyncStats
from app.models import SyncRun, SyncRunStatus


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

    async def create_running(self, *, source_id: str | None = None) -> SyncRun:
        """Create a running sync run keyed by source_id."""
        run = await self.try_create_running(source_id=source_id)
        if run is None:
            raise RuntimeError("running sync already exists for source")
        return run

    async def try_create_running(self, *, source_id: str | None = None) -> SyncRun | None:
        """Create a running sync run, returning None on unique-running conflict."""
        now = _now_naive_utc()
        run = SyncRun(
            source_id=source_id,
            status=SyncRunStatus.running,
            started_at=now,
            created_at=now,
        )
        self.session.add(run)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            return None
        await self.session.refresh(run)
        return run

    async def create_finished(
        self,
        *,
        source_id: str | None = None,
        status: SyncRunStatus,
        error_summary: str | None = None,
        stats: SourceSyncStats | None = None,
    ) -> SyncRun:
        """Create a finished (terminal) sync run keyed by source_id."""
        now = _now_naive_utc()
        run = SyncRun(
            source_id=source_id,
            status=status,
            started_at=now,
            finished_at=now,
            error_summary=error_summary,
            created_at=now,
        )
        _apply_stats(run, stats)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    # ------------------------------------------------------------------ #
    # Authoritative source_id-based helpers (Phase 3 cutover)              #
    # ------------------------------------------------------------------ #

    async def get_running_by_source_id(self, *, source_id: str) -> SyncRun | None:
        """Authoritative: find a running sync run for a given source_id."""
        result = await self.session.exec(
            select(SyncRun)
            .where(
                SyncRun.source_id == source_id,
                SyncRun.status == SyncRunStatus.running,
            )
            .order_by(SyncRun.started_at.desc())
        )
        return result.first()

    async def has_any_for_source_id(self, *, source_id: str) -> bool:
        """Authoritative: return True if any sync run references the given source_id."""
        result = await self.session.exec(
            select(SyncRun.id).where(SyncRun.source_id == source_id).limit(1)
        )
        return result.first() is not None

    async def finish(
        self,
        *,
        run: SyncRun,
        status: SyncRunStatus,
        error_summary: str | None = None,
        stats: SourceSyncStats | None = None,
    ) -> SyncRun:
        run.status = status
        run.finished_at = _now_naive_utc()
        run.error_summary = error_summary
        _apply_stats(run, stats)
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run
