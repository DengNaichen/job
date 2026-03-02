"""Repository helpers for persisted job embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import JobEmbedding


@dataclass(frozen=True)
class JobEmbeddingUpsertPayload:
    """Payload for writing one job embedding row for an active target."""

    job_id: str
    embedding: list[float]
    content_fingerprint: str | None


class JobEmbeddingRepository:
    """Repository for JobEmbedding entity database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def _target_filters(
        *,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
    ) -> tuple:
        return (
            JobEmbedding.embedding_kind == embedding_kind,
            JobEmbedding.embedding_target_revision == embedding_target_revision,
            JobEmbedding.embedding_model == embedding_model,
            JobEmbedding.embedding_dim == embedding_dim,
        )

    async def get_by_job_and_target(
        self,
        *,
        job_id: str,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
    ) -> JobEmbedding | None:
        """Return the active-target embedding row for one job, if present."""
        statement = (
            select(JobEmbedding)
            .where(
                JobEmbedding.job_id == job_id,
                *self._target_filters(
                    embedding_kind=embedding_kind,
                    embedding_target_revision=embedding_target_revision,
                    embedding_model=embedding_model,
                    embedding_dim=embedding_dim,
                ),
            )
            .limit(1)
        )
        result = await self.session.exec(statement)
        return result.first()

    async def list_by_job_ids_and_target(
        self,
        *,
        job_ids: Sequence[str],
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
    ) -> dict[str, JobEmbedding]:
        """Fetch active-target rows keyed by job_id."""
        ids = [job_id for job_id in job_ids if job_id]
        if not ids:
            return {}

        statement = select(JobEmbedding).where(
            JobEmbedding.job_id.in_(ids),
            *self._target_filters(
                embedding_kind=embedding_kind,
                embedding_target_revision=embedding_target_revision,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
            ),
        )
        result = await self.session.exec(statement)
        rows = list(result.all())
        return {row.job_id: row for row in rows}

    async def list_fresh_job_ids_for_target(
        self,
        *,
        job_content_fingerprints: dict[str, str | None],
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
    ) -> set[str]:
        """Return job IDs whose active-target row fingerprint matches current job fingerprint."""
        if not job_content_fingerprints:
            return set()

        rows_by_job_id = await self.list_by_job_ids_and_target(
            job_ids=list(job_content_fingerprints),
            embedding_kind=embedding_kind,
            embedding_target_revision=embedding_target_revision,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )

        fresh_ids: set[str] = set()
        for job_id, fingerprint in job_content_fingerprints.items():
            row = rows_by_job_id.get(job_id)
            if row is None:
                continue
            if row.content_fingerprint == fingerprint:
                fresh_ids.add(job_id)
        return fresh_ids

    async def upsert_for_target(
        self,
        *,
        job_id: str,
        embedding: list[float],
        content_fingerprint: str | None,
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        updated_at: datetime | None = None,
    ) -> JobEmbedding:
        """Create or refresh one active-target row for a job."""
        row = await self.get_by_job_and_target(
            job_id=job_id,
            embedding_kind=embedding_kind,
            embedding_target_revision=embedding_target_revision,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
        )
        now = updated_at or datetime.now(timezone.utc)
        if row is None:
            row = JobEmbedding(
                job_id=job_id,
                embedding_kind=embedding_kind,
                embedding_target_revision=embedding_target_revision,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                embedding=embedding,
                content_fingerprint=content_fingerprint,
                created_at=now,
                updated_at=now,
            )
            self.session.add(row)
            await self.session.flush()
            return row

        row.embedding = embedding
        row.content_fingerprint = content_fingerprint
        row.updated_at = now
        self.session.add(row)
        await self.session.flush()
        return row

    async def upsert_many_for_target(
        self,
        *,
        rows: Sequence[JobEmbeddingUpsertPayload],
        embedding_kind: str,
        embedding_target_revision: int,
        embedding_model: str,
        embedding_dim: int,
        updated_at: datetime | None = None,
    ) -> int:
        """Create or refresh multiple active-target rows in the current transaction."""
        count = 0
        for row in rows:
            await self.upsert_for_target(
                job_id=row.job_id,
                embedding=row.embedding,
                content_fingerprint=row.content_fingerprint,
                embedding_kind=embedding_kind,
                embedding_target_revision=embedding_target_revision,
                embedding_model=embedding_model,
                embedding_dim=embedding_dim,
                updated_at=updated_at,
            )
            count += 1
        return count
