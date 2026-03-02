"""
Unit tests for SourceService.

Covers:
- delete_source: reference guards (sync_run, job — authoritative source_id path)
- update_source: mutation guards when jobs exist
"""

import pytest

from sqlmodel.ext.asyncio.session import AsyncSession


class TestSourceServiceDelete:
    """Tests for SourceService delete behavior."""

    @pytest.mark.asyncio
    async def test_delete_source_without_sync_runs_succeeds(self, session: AsyncSession):
        from app.models import PlatformType, Source
        from app.repositories.source import SourceRepository
        from app.repositories.sync_run import SyncRunRepository
        from app.services.application.source import SourceService

        source_repo = SourceRepository(session)
        sync_run_repo = SyncRunRepository(session)
        service = SourceService(source_repo, sync_run_repo)
        source = await source_repo.create(
            Source(
                name="Stripe",
                name_normalized="stripe",
                platform=PlatformType.GREENHOUSE,
                identifier="stripe",
            )
        )

        await service.delete_source(source.id)

        assert await source_repo.get_by_id(source.id) is None

    @pytest.mark.asyncio
    async def test_delete_source_with_sync_runs_raises_has_references(self, session: AsyncSession):
        from app.models import PlatformType, Source
        from app.repositories.source import SourceRepository
        from app.repositories.sync_run import SyncRunRepository
        from app.services.application.source import HasReferencesError, SourceService

        source_repo = SourceRepository(session)
        sync_run_repo = SyncRunRepository(session)
        service = SourceService(source_repo, sync_run_repo)
        source = await source_repo.create(
            Source(
                name="Stripe",
                name_normalized="stripe",
                platform=PlatformType.GREENHOUSE,
                identifier="stripe",
            )
        )
        source_id = source.id
        await sync_run_repo.create_running(
            source_id=str(source_id),
        )

        with pytest.raises(HasReferencesError):
            await service.delete_source(source_id)

    @pytest.mark.asyncio
    async def test_delete_source_blocked_by_sync_run_with_source_id_only(
        self, session: AsyncSession
    ):
        """delete_source raises HasReferencesError when a sync run is linked via source_id
        (authoritative path — no legacy source string fallback involved)."""
        from app.models import PlatformType, Source
        from app.repositories.source import SourceRepository
        from app.repositories.sync_run import SyncRunRepository
        from app.services.application.source import HasReferencesError, SourceService

        source_repo = SourceRepository(session)
        sync_run_repo = SyncRunRepository(session)
        service = SourceService(source_repo, sync_run_repo)
        source = await source_repo.create(
            Source(
                name="Vercel",
                name_normalized="vercel",
                platform=PlatformType.GREENHOUSE,
                identifier="vercel",
            )
        )
        source_id = source.id  # capture before create_running commits and expires the session
        # Create sync run with source_id ONLY — no legacy source string match.
        await sync_run_repo.create_running(
            source_id=str(source_id),
        )

        with pytest.raises(HasReferencesError):
            await service.delete_source(source_id)

    @pytest.mark.asyncio
    async def test_delete_source_with_job_refs_raises_has_references(self, session: AsyncSession):
        """delete_source raises HasReferencesError when jobs are linked by source_id."""
        from app.models import Job, JobStatus, PlatformType, Source
        from app.repositories.job import JobRepository
        from app.repositories.source import SourceRepository
        from app.services.application.source import HasReferencesError, SourceService

        source_repo = SourceRepository(session)
        job_repo = JobRepository(session)
        service = SourceService(source_repo, job_repository=job_repo)
        source = await source_repo.create(
            Source(
                name="Acme",
                name_normalized="acme",
                platform=PlatformType.GREENHOUSE,
                identifier="acme",
            )
        )
        # Direct-insert a job with source_id pointing at this source
        job = Job(
            source_id=str(source.id),
            external_job_id="job-42",
            title="SWE",
            apply_url="https://acme.com/jobs/42",
            status=JobStatus.open,
        )
        session.add(job)
        await session.flush()  # flush so the job is visible to queries without expiring source

        with pytest.raises(HasReferencesError):
            await service.delete_source(source.id)

    @pytest.mark.asyncio
    async def test_update_source_platform_blocked_when_jobs_exist(self, session: AsyncSession):
        """update_source raises HasMutationBlockError when jobs reference the source."""
        from app.models import Job, JobStatus, PlatformType, Source
        from app.repositories.job import JobRepository
        from app.repositories.source import SourceRepository
        from app.schemas.source import SourceUpdate
        from app.services.application.source import HasMutationBlockError, SourceService

        source_repo = SourceRepository(session)
        job_repo = JobRepository(session)
        service = SourceService(source_repo, job_repository=job_repo)
        source = await source_repo.create(
            Source(
                name="Beta Corp",
                name_normalized="beta corp",
                platform=PlatformType.GREENHOUSE,
                identifier="betacorp",
            )
        )
        # Insert a job tied to this source
        job = Job(
            source_id=str(source.id),
            external_job_id="j-1",
            title="Dev",
            apply_url="https://beta.com/jobs/1",
            status=JobStatus.open,
        )
        session.add(job)
        await session.flush()  # flush so the job is visible to queries without expiring source

        # Attempting to change platform should be blocked
        with pytest.raises(HasMutationBlockError):
            await service.update_source(source.id, SourceUpdate(platform="lever"))
