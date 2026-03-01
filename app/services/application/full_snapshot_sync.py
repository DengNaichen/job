from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.contracts.sync import SourceSyncResult, SourceSyncStats
from app.ingest.fetchers.base import BaseFetcher
from app.ingest.mappers.base import BaseMapper
from app.models import Job, JobStatus, Source, build_source_key
from app.repositories.job import JobRepository
from app.services.infra.blob_storage import JobBlobManager, JobBlobPointers


def _to_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _now_naive_utc() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class FullSnapshotSyncError(Exception):
    """Raised when one source snapshot cannot be fully reconciled."""


class FullSnapshotSyncService:
    """Same-source full snapshot reconcile service."""

    def __init__(
        self,
        session: AsyncSession,
        job_repository: JobRepository | None = None,
        blob_manager: JobBlobManager | None = None,
    ):
        self.session = session
        self.job_repository = job_repository or JobRepository(session)
        self.blob_manager = blob_manager or JobBlobManager()

    async def sync_source(
        self,
        *,
        source: Source,
        fetcher: BaseFetcher,
        mapper: BaseMapper,
        include_content: bool = True,
        dry_run: bool = False,
    ) -> SourceSyncResult:
        source_key = build_source_key(source.platform, source.identifier)
        source_id = str(source.id)
        stats = SourceSyncStats()

        try:
            raw_jobs = await fetcher.fetch(source.identifier, include_content=include_content)
            stats.fetched_count = len(raw_jobs)

            mapped_payloads: list[dict[str, Any]] = []
            for raw_job in raw_jobs:
                mapped = mapper.map(raw_job)
                payload = mapped.model_dump()
                external_job_id = str(payload.get("external_job_id") or "").strip()
                if not external_job_id:
                    raise FullSnapshotSyncError("Mapped job is missing external_job_id")
                payload["external_job_id"] = external_job_id
                payload["source"] = source_key
                mapped_payloads.append(payload)

            stats.mapped_count = len(mapped_payloads)
            unique_payloads = self._dedupe_by_external_job_id(mapped_payloads)
            stats.unique_count = len(unique_payloads)
            stats.deduped_by_external_id = stats.mapped_count - stats.unique_count

            sync_started_at = _now_naive_utc()
            existing_rows = await self.job_repository.list_by_source_and_external_ids(
                source=source_key,
                external_job_ids=[payload["external_job_id"] for payload in unique_payloads],
            )
            existing_map = {str(job.external_job_id): job for job in existing_rows}

            staged_jobs: list[Job] = []
            for payload in unique_payloads:
                existing = existing_map.get(str(payload["external_job_id"]))
                if existing is None:
                    job = self._build_new_job(payload, sync_started_at)
                    await self.blob_manager.sync_job_blobs(job)
                    staged_jobs.append(job)
                    stats.inserted_count += 1
                    continue

                existing_pointers = JobBlobPointers.from_job(existing)
                self._update_existing_job(existing, payload, sync_started_at)
                await self.blob_manager.sync_job_blobs(
                    existing,
                    existing_pointers=existing_pointers,
                )
                staged_jobs.append(existing)
                stats.updated_count += 1

            if staged_jobs:
                await self.job_repository.save_all_no_commit(staged_jobs)
                await self.job_repository.flush()

            if dry_run:
                await self.session.rollback()
                stats.closed_count = 0
            else:
                stats.closed_count = await self.job_repository.bulk_close_missing_for_source(
                    source=source_key,
                    seen_at_before=sync_started_at,
                    updated_at=_now_naive_utc(),
                )
                await self.session.commit()

            return SourceSyncResult(
                source_id=source_id,
                source_key=source_key,
                ok=True,
                stats=stats,
            )
        except Exception as exc:
            await self.session.rollback()
            stats.failed_count = max(
                stats.unique_count,
                stats.mapped_count,
                stats.fetched_count,
                1,
            )
            return SourceSyncResult(
                source_id=source_id,
                source_key=source_key,
                ok=False,
                stats=stats,
                error=str(exc),
            )

    @staticmethod
    def _dedupe_by_external_job_id(mapped_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for payload in mapped_payloads:
            deduped[str(payload["external_job_id"])] = payload
        return list(deduped.values())

    @staticmethod
    def _build_new_job(payload: dict[str, Any], sync_started_at: datetime) -> Job:
        data = dict(payload)
        data["published_at"] = _to_naive_utc(data.get("published_at"))
        data["source_updated_at"] = _to_naive_utc(data.get("source_updated_at"))
        data["status"] = JobStatus.open
        data["ingested_at"] = sync_started_at
        data["last_seen_at"] = sync_started_at
        data["created_at"] = sync_started_at
        data["updated_at"] = sync_started_at
        return Job(**data)

    @staticmethod
    def _update_existing_job(
        job: Job,
        payload: dict[str, Any],
        sync_started_at: datetime,
    ) -> None:
        normalized_payload = dict(payload)
        normalized_payload["published_at"] = _to_naive_utc(normalized_payload.get("published_at"))
        normalized_payload["source_updated_at"] = _to_naive_utc(
            normalized_payload.get("source_updated_at")
        )
        for key, value in normalized_payload.items():
            setattr(job, key, value)
        job.status = JobStatus.open
        job.last_seen_at = sync_started_at
        job.updated_at = sync_started_at
