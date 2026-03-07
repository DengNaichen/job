"""Job repository for database operations."""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, update
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, JobEmbedding, JobStatus, Location, PlatformType, Source
from app.models.job_location import JobLocation


@dataclass(frozen=True)
class EmbeddableJobRow:
    """Projection used for generating active-target embeddings."""

    id: str
    title: str
    description: str
    structured_jd: object | None
    content_fingerprint: str | None


@dataclass(frozen=True)
class SnapshotRefreshCandidateRow:
    """Projection used for source-scoped snapshot embedding refresh."""

    id: str
    title: str
    description: str
    structured_jd: object | None
    content_fingerprint: str | None


class JobRepository:
    """Repository for Job entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _split_source_key(source_key: str) -> tuple[PlatformType, str] | None:
        if ":" not in source_key:
            return None
        platform_str, identifier = source_key.split(":", 1)
        platform_str = platform_str.strip().lower()
        identifier = identifier.strip()
        if not platform_str or not identifier:
            return None
        try:
            return PlatformType(platform_str), identifier
        except ValueError:
            return None

    async def create(self, job: Job) -> Job:
        """Create a new job."""
        job_id = str(job.id)
        self.session.add(job)
        await self.session.commit()
        reloaded = await self.get_by_id(job_id)
        return reloaded or job

    async def get_by_id(self, job_id: str) -> Job | None:
        """Get a job by ID."""
        statement = (
            select(Job)
            .where(Job.id == job_id)
            .options(selectinload(Job.source_record))
            .options(selectinload(Job.job_locations).selectinload(JobLocation.location))
        )
        result = await self.session.exec(statement)
        return result.first()

    async def list_by_ids(self, job_ids: list[str]) -> list[Job]:
        """Get jobs by IDs while preserving input order."""
        if not job_ids:
            return []
        statement = (
            select(Job)
            .where(Job.id.in_(job_ids))
            .options(selectinload(Job.source_record))
            .options(selectinload(Job.job_locations).selectinload(JobLocation.location))
        )
        result = await self.session.execute(statement)
        jobs = list(result.scalars().all())
        jobs_by_id = {str(job.id): job for job in jobs}
        return [jobs_by_id[job_id] for job_id in job_ids if job_id in jobs_by_id]

    # ------------------------------------------------------------------ #
    # Authoritative source_id-based helpers (Phase 3 cutover)              #
    # ------------------------------------------------------------------ #

    async def list_by_source_id_and_external_ids(
        self,
        source_id: str,
        external_job_ids: list[str],
    ) -> list[Job]:
        """Authoritative: get jobs for one same-source snapshot keyed by source_id."""
        if not external_job_ids:
            return []
        result = await self.session.exec(
            select(Job).where(
                Job.source_id == source_id,
                Job.external_job_id.in_(external_job_ids),
            )
        )
        return list(result.all())

    async def bulk_close_missing_for_source_id(
        self,
        *,
        source_id: str,
        seen_at_before: datetime,
        updated_at: datetime,
    ) -> int:
        """Authoritative: close stale open jobs for a source_id not seen in this snapshot."""
        result = await self.session.exec(
            update(Job)
            .where(
                Job.source_id == source_id,
                Job.status == JobStatus.open,
                Job.last_seen_at < seen_at_before,
            )
            .values(
                status=JobStatus.closed,
                updated_at=updated_at,
            )
        )
        return int(result.rowcount or 0)

    async def source_id_reference_exists(self, source_id: str) -> bool:
        """Return True if any job row references the given source_id."""
        result = await self.session.exec(select(Job.id).where(Job.source_id == source_id).limit(1))
        return result.first() is not None

    # ------------------------------------------------------------------ #
    # Legacy string-based helpers                                          #
    # LEGACY-FALLBACK: remove after enforcement revision (Phase 6).        #
    # ------------------------------------------------------------------ #

    async def list_by_source_and_external_ids(
        self,
        source: str,
        external_job_ids: list[str],
    ) -> list[Job]:
        """Compatibility helper: source-key lookup mapped to authoritative source_id."""
        if not external_job_ids:
            return []

        parsed = self._split_source_key(source)
        if parsed is None:
            return []
        platform, identifier = parsed

        result = await self.session.exec(
            select(Job)
            .join(Source, Source.id == Job.source_id)
            .where(
                Source.platform == platform,
                Source.identifier == identifier,
                Job.external_job_id.in_(external_job_ids),
            )
        )
        return list(result.all())

    async def has_any_for_source(self, *, source: str) -> bool:
        """Compatibility helper: source-key lookup mapped to authoritative source_id."""
        parsed = self._split_source_key(source)
        if parsed is None:
            return False
        platform, identifier = parsed
        result = await self.session.exec(
            select(Job.id)
            .join(Source, Source.id == Job.source_id)
            .where(Source.platform == platform, Source.identifier == identifier)
            .limit(1)
        )
        return result.first() is not None

    async def list_jobs(
        self,
        skip: int = 0,
        limit: int = 100,
        status: JobStatus | None = None,
    ) -> list[Job]:
        """List jobs with optional pagination and status filter."""
        statement = (
            select(Job)
            .offset(skip)
            .limit(limit)
            .options(selectinload(Job.source_record))
            .options(selectinload(Job.job_locations).selectinload(JobLocation.location))
        )
        if status is not None:
            statement = statement.where(Job.status == status)
        result = await self.session.exec(statement)
        return list(result.all())

    async def update(self, job: Job) -> Job:
        """Update an existing job."""
        job_id = str(job.id)
        self.session.add(job)
        await self.session.commit()
        reloaded = await self.get_by_id(job_id)
        return reloaded or job

    async def save_all(self, jobs: list[Job]) -> None:
        """Save a batch of existing jobs in one commit."""
        for job in jobs:
            self.session.add(job)
        await self.session.commit()

    async def save_all_no_commit(self, jobs: list[Job]) -> None:
        """Stage a batch of jobs in the current transaction without committing."""
        for job in jobs:
            self.session.add(job)

    async def flush(self) -> None:
        """Flush the current unit of work without committing."""
        await self.session.flush()

    async def bulk_close_missing_for_source(
        self,
        *,
        source: str,
        seen_at_before: datetime,
        updated_at: datetime,
    ) -> int:
        """Compatibility helper: close by source-key via authoritative source_id."""
        parsed = self._split_source_key(source)
        if parsed is None:
            return 0
        platform, identifier = parsed
        source_id_result = await self.session.exec(
            select(Source.id).where(Source.platform == platform, Source.identifier == identifier).limit(1)
        )
        source_id = source_id_result.first()
        if source_id is None:
            return 0

        result = await self.session.exec(
            update(Job)
            .where(
                Job.source_id == str(source_id),
                Job.status == JobStatus.open,
                Job.last_seen_at < seen_at_before,
            )
            .values(
                status=JobStatus.closed,
                updated_at=updated_at,
            )
        )
        return int(result.rowcount or 0)

    async def delete(self, job: Job) -> None:
        """Delete a job."""
        await self.session.delete(job)
        await self.session.commit()

    async def list_pending_structured_jd(
        self,
        limit: int = 5,
        *,
        version_only: bool = False,
        exclude_job_ids: Collection[str] | None = None,
    ) -> list[Job]:
        """List jobs eligible for structured_jd extraction."""
        statement = select(Job).where(
            (Job.description_html_key.is_not(None)) | (Job.description_plain.is_not(None))
        )
        if version_only:
            statement = statement.where(Job.structured_jd.is_not(None)).where(
                Job.structured_jd_version < 3
            )
        else:
            statement = statement.where(
                (Job.structured_jd.is_(None)) | (Job.structured_jd_version < 3)
            )
        if exclude_job_ids:
            statement = statement.where(Job.id.not_in(list(exclude_job_ids)))
        statement = statement.order_by(Job.updated_at, Job.id).limit(limit)
        result = await self.session.exec(statement)
        return list(result.all())

    async def list_jobs_for_location_backfill(
        self,
        last_id: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs for location backfill using keyset pagination."""
        statement = select(Job)
        if last_id:
            statement = statement.where(Job.id > last_id)
        statement = statement.order_by(Job.id).limit(limit)
        result = await self.session.exec(statement)
        return list(result.all())

    async def list_jobs_for_country_backfill(
        self,
        last_id: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs whose primary canonical location is missing or lacks a country code."""
        statement = (
            select(Job)
            .outerjoin(JobLocation, and_(Job.id == JobLocation.job_id, JobLocation.is_primary.is_(True)))
            .outerjoin(Location, Location.id == JobLocation.location_id)
            .where(or_(JobLocation.job_id.is_(None), Location.country_code.is_(None)))
        )
        if last_id:
            statement = statement.where(Job.id > last_id)
        statement = statement.order_by(Job.id).limit(limit)
        result = await self.session.exec(statement)
        return list(result.all())

    async def list_jobs_missing_canonical_locations(
        self,
        last_id: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """List jobs that do not have any associated JobLocation links."""
        from app.models.job_location import JobLocation

        statement = (
            select(Job)
            .outerjoin(JobLocation, Job.id == JobLocation.job_id)
            .where(JobLocation.job_id.is_(None))
        )
        if last_id:
            statement = statement.where(Job.id > last_id)
        statement = statement.order_by(Job.id).limit(limit)
        result = await self.session.exec(statement)
        return list(result.all())

    # ------------------------------------------------------------------ #
    # Embedding storage redesign helpers                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _target_join(
        *,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
    ):
        return and_(
            JobEmbedding.job_id == Job.id,
            JobEmbedding.embedding_kind == embedding_kind,
            JobEmbedding.embedding_target_revision == embedding_target_revision,
            JobEmbedding.embedding_model == embedding_model,
            JobEmbedding.embedding_dim == embedding_dim,
        )

    @staticmethod
    def _embeddable_description_expr():
        return func.nullif(Job.description_plain, "")

    async def list_embeddable_jobs_for_active_target(
        self,
        *,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        last_id: str | None = None,
        limit: int = 100,
        require_structured: bool = False,
        force: bool = False,
    ) -> list[EmbeddableJobRow]:
        """List embeddable jobs whose active target is missing or stale."""
        description_expr = self._embeddable_description_expr().label("description")
        statement = (
            select(Job.id, Job.title, description_expr, Job.structured_jd, Job.content_fingerprint)
            .select_from(Job)
            .outerjoin(
                JobEmbedding,
                self._target_join(
                    embedding_kind=embedding_kind,
                    embedding_target_revision=embedding_target_revision,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                ),
            )
            .where(description_expr.is_not(None))
        )
        if require_structured:
            statement = statement.where(
                Job.structured_jd.is_not(None),
                func.coalesce(Job.structured_jd_version, 0) >= 3,
            )
        if last_id is not None:
            statement = statement.where(Job.id > last_id)
        if not force:
            statement = statement.where(
                or_(
                    JobEmbedding.id.is_(None),
                    JobEmbedding.content_fingerprint.is_distinct_from(Job.content_fingerprint),
                )
            )

        statement = statement.order_by(Job.id).limit(limit)
        result = await self.session.exec(statement)
        rows = result.all()
        return [
            EmbeddableJobRow(
                id=row.id,
                title=row.title,
                description=row.description,
                structured_jd=row.structured_jd,
                content_fingerprint=row.content_fingerprint,
            )
            for row in rows
        ]

    async def count_jobs_missing_or_stale_active_target(
        self,
        *,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        require_structured: bool = False,
        require_embeddable_content: bool = True,
        force: bool = False,
    ) -> int:
        """Count jobs that still need active-target embedding writes."""
        description_expr = self._embeddable_description_expr()
        statement = (
            select(func.count(Job.id))
            .select_from(Job)
            .outerjoin(
                JobEmbedding,
                self._target_join(
                    embedding_kind=embedding_kind,
                    embedding_target_revision=embedding_target_revision,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                ),
            )
        )
        if require_structured:
            statement = statement.where(
                Job.structured_jd.is_not(None),
                func.coalesce(Job.structured_jd_version, 0) >= 3,
            )
        if require_embeddable_content:
            statement = statement.where(description_expr.is_not(None))
        if force:
            if not require_embeddable_content:
                statement = statement.where(description_expr.is_not(None))
        else:
            statement = statement.where(
                or_(
                    JobEmbedding.id.is_(None),
                    JobEmbedding.content_fingerprint.is_distinct_from(Job.content_fingerprint),
                )
            )
        result = await self.session.exec(statement)
        return int(result.one())

    async def count_fresh_active_target_jobs(
        self,
        *,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        require_structured: bool = False,
    ) -> int:
        """Count jobs whose active-target row is already fresh."""
        description_expr = self._embeddable_description_expr()
        statement = (
            select(func.count(Job.id))
            .select_from(Job)
            .join(
                JobEmbedding,
                self._target_join(
                    embedding_kind=embedding_kind,
                    embedding_target_revision=embedding_target_revision,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                ),
            )
            .where(
                description_expr.is_not(None),
                JobEmbedding.content_fingerprint.is_not_distinct_from(Job.content_fingerprint),
            )
        )
        if require_structured:
            statement = statement.where(
                Job.structured_jd.is_not(None),
                func.coalesce(Job.structured_jd_version, 0) >= 3,
            )
        result = await self.session.exec(statement)
        return int(result.one())

    async def list_snapshot_refresh_candidates_for_active_target(
        self,
        *,
        source_id: str,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        last_id: str | None = None,
        limit: int = 100,
        require_structured: bool = False,
        force: bool = False,
    ) -> list[SnapshotRefreshCandidateRow]:
        """List source-scoped open jobs whose active target is missing or stale."""
        description_expr = self._embeddable_description_expr().label("description")
        statement = (
            select(Job.id, Job.title, description_expr, Job.structured_jd, Job.content_fingerprint)
            .select_from(Job)
            .outerjoin(
                JobEmbedding,
                self._target_join(
                    embedding_kind=embedding_kind,
                    embedding_target_revision=embedding_target_revision,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                ),
            )
            .where(
                Job.source_id == source_id,
                Job.status == JobStatus.open,
                description_expr.is_not(None),
            )
        )
        if require_structured:
            statement = statement.where(
                Job.structured_jd.is_not(None),
                func.coalesce(Job.structured_jd_version, 0) >= 3,
            )
        if last_id is not None:
            statement = statement.where(Job.id > last_id)
        if not force:
            statement = statement.where(
                or_(
                    JobEmbedding.id.is_(None),
                    JobEmbedding.content_fingerprint.is_distinct_from(Job.content_fingerprint),
                )
            )

        statement = statement.order_by(Job.id).limit(limit)
        result = await self.session.exec(statement)
        rows = result.all()
        return [
            SnapshotRefreshCandidateRow(
                id=row.id,
                title=row.title,
                description=row.description,
                structured_jd=row.structured_jd,
                content_fingerprint=row.content_fingerprint,
            )
            for row in rows
        ]
