from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential

from app.contracts.sync import SourceSyncResult
from app.core.database import engine as default_engine
from app.ingest.fetchers.base import BaseFetcher
from app.ingest.mappers.base import BaseMapper
from app.models import PlatformType, Source, SyncRun, SyncRunStatus
from app.repositories.job import JobRepository
from app.repositories.sync_run import SyncRunRepository
from app.services.application.full_snapshot_sync import FullSnapshotSyncService
from app.services.application.sync_handlers import (
    PLATFORM_SYNC_HANDLERS,
    PlatformSyncHandlers,
)


class SourceSyncAttemptFailed(Exception):
    """Raised to trigger retry when a source sync result is unsuccessful."""

    def __init__(self, result: SourceSyncResult):
        self.result = result
        super().__init__(result.error or "source sync failed")


class SyncService:
    """Orchestrates one source sync run with overlap guard and retries."""

    def __init__(self, engine: AsyncEngine = default_engine):
        self.engine = engine

    async def sync_source(
        self,
        *,
        source: Source,
        include_content: bool = True,
        dry_run: bool = False,
        retry_attempts: int = 3,
    ) -> SyncRun:
        handlers = self._resolve_handlers(source.platform)

        async with AsyncSession(self.engine) as tracking_session:
            sync_run_repository = SyncRunRepository(tracking_session)
            # Authoritative overlap check by source_id
            running = await sync_run_repository.get_running_by_source_id(source_id=str(source.id))
            if running is not None:
                return await sync_run_repository.create_finished(
                    source_id=str(source.id),
                    status=SyncRunStatus.failed,
                    error_summary="overlap: source already running",
                )

            if handlers is None:
                return await sync_run_repository.create_finished(
                    source_id=str(source.id),
                    status=SyncRunStatus.failed,
                    error_summary=f"unsupported platform: {source.platform.value}",
                )

            sync_run = await sync_run_repository.create_running(
                source_id=str(source.id),
            )
            fetcher = handlers.fetcher_cls()
            mapper = handlers.mapper_cls()
            last_result: SourceSyncResult | None = None

            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(max(1, retry_attempts)),
                    wait=wait_exponential(multiplier=1, min=1, max=4),
                    reraise=True,
                ):
                    with attempt:
                        result = await self._execute_snapshot_sync(
                            source=source,
                            fetcher=fetcher,
                            mapper=mapper,
                            include_content=include_content,
                            dry_run=dry_run,
                        )
                        if not result.ok:
                            last_result = result
                            raise SourceSyncAttemptFailed(result)
                        last_result = result

                if last_result is None:
                    return await sync_run_repository.finish(
                        run=sync_run,
                        status=SyncRunStatus.failed,
                        error_summary="source sync produced no result",
                    )

                return await sync_run_repository.finish(
                    run=sync_run,
                    status=SyncRunStatus.success,
                    stats=last_result.stats,
                )
            except SourceSyncAttemptFailed as exc:
                failed_result = last_result or exc.result
                return await sync_run_repository.finish(
                    run=sync_run,
                    status=SyncRunStatus.failed,
                    error_summary=failed_result.error or "source sync failed",
                    stats=failed_result.stats,
                )
            except Exception as exc:
                return await sync_run_repository.finish(
                    run=sync_run,
                    status=SyncRunStatus.failed,
                    error_summary=str(exc),
                )

    @staticmethod
    def _resolve_handlers(platform: PlatformType) -> PlatformSyncHandlers | None:
        return PLATFORM_SYNC_HANDLERS.get(platform)

    async def _execute_snapshot_sync(
        self,
        *,
        source: Source,
        fetcher: BaseFetcher,
        mapper: BaseMapper,
        include_content: bool,
        dry_run: bool,
    ) -> SourceSyncResult:
        async with AsyncSession(self.engine) as session:
            service = FullSnapshotSyncService(
                session=session,
                job_repository=JobRepository(session),
            )
            return await service.sync_source(
                source=source,
                fetcher=fetcher,
                mapper=mapper,
                include_content=include_content,
                dry_run=dry_run,
            )
