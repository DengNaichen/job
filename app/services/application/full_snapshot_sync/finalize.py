from __future__ import annotations

from datetime import datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from app.contracts.sync import SourceSyncStats
from app.repositories.job import JobRepository

from .time_utils import now_naive_utc


async def finalize_snapshot(
    *,
    session: AsyncSession,
    job_repository: JobRepository,
    source_id: str,
    sync_started_at: datetime,
    dry_run: bool,
    stats: SourceSyncStats,
) -> None:
    if dry_run:
        await session.rollback()
        stats.closed_count = 0
        return

    stats.closed_count = await job_repository.bulk_close_missing_for_source_id(
        source_id=source_id,
        seen_at_before=sync_started_at,
        updated_at=now_naive_utc(),
    )
    await session.commit()
