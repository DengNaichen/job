from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from app.contracts.sync import SourceSyncStats
from app.models import Job, JobStatus
from app.repositories.job import JobRepository
from app.services.application.blob.job_blob import JobBlobManager, JobBlobPointers
from app.services.application.job_payload import (
    drop_legacy_job_payload_fields,
    hydrate_description_plain,
)

from .time_utils import to_naive_utc

DEFAULT_BLOB_SYNC_CONCURRENCY = 16

async def build_existing_map(
    *,
    job_repository: JobRepository,
    source_id: str,
    unique_payloads: list[dict[str, Any]],
) -> dict[str, Job]:
    existing_rows = await job_repository.list_by_source_id_and_external_ids(
        source_id=source_id,
        external_job_ids=[payload["external_job_id"] for payload in unique_payloads],
    )
    return {str(job.external_job_id): job for job in existing_rows}


async def stage_jobs_for_snapshot(
    *,
    blob_manager: JobBlobManager,
    unique_payloads: list[dict[str, Any]],
    existing_map: dict[str, Job],
    sync_started_at: datetime,
    stats: SourceSyncStats,
    blob_sync_concurrency: int = DEFAULT_BLOB_SYNC_CONCURRENCY,
) -> list[Job]:
    concurrency = max(1, int(blob_sync_concurrency))
    semaphore = asyncio.Semaphore(concurrency)
    blob_fields = {"description_html", "raw_payload"}

    async def process_payload(payload: dict[str, Any]) -> tuple[Job, bool]:
        async with semaphore:
            description_html = payload.get("description_html")
            raw_payload = payload.get("raw_payload")
            existing = existing_map.get(str(payload["external_job_id"]))
            if existing is None:
                job = build_new_job(payload, sync_started_at)
                await blob_manager.sync_job_blobs(
                    job,
                    explicit_fields=blob_fields,
                    description_html=description_html,
                    raw_payload=raw_payload,
                )
                return job, True

            existing_pointers = JobBlobPointers.from_job(existing)
            update_existing_job(existing, payload, sync_started_at)
            await blob_manager.sync_job_blobs(
                existing,
                existing_pointers=existing_pointers,
                explicit_fields=blob_fields,
                description_html=description_html,
                raw_payload=raw_payload,
            )
            return existing, False

    staged_jobs: list[Job] = []
    results = await asyncio.gather(*(process_payload(payload) for payload in unique_payloads))
    for job, inserted in results:
        staged_jobs.append(job)
        if inserted:
            stats.inserted_count += 1
        else:
            stats.updated_count += 1
    return staged_jobs


async def persist_staged_jobs(*, job_repository: JobRepository, staged_jobs: list[Job]) -> None:
    await job_repository.save_all_no_commit(staged_jobs)
    await job_repository.flush()


def build_new_job(payload: dict[str, Any], sync_started_at: datetime) -> Job:
    data = dict(payload)
    hydrate_description_plain(data, description_html=data.get("description_html"))
    data["published_at"] = to_naive_utc(data.get("published_at"))
    data["source_updated_at"] = to_naive_utc(data.get("source_updated_at"))
    data["status"] = JobStatus.open
    data["last_seen_at"] = sync_started_at
    data["created_at"] = sync_started_at
    data["updated_at"] = sync_started_at
    data.pop("description_html", None)
    data.pop("raw_payload", None)
    drop_legacy_job_payload_fields(data, include_source=True)
    return Job(**data)


def update_existing_job(
    job: Job,
    payload: dict[str, Any],
    sync_started_at: datetime,
) -> None:
    normalized_payload = dict(payload)
    hydrate_description_plain(
        normalized_payload,
        description_html=normalized_payload.get("description_html"),
    )
    normalized_payload["published_at"] = to_naive_utc(normalized_payload.get("published_at"))
    normalized_payload["source_updated_at"] = to_naive_utc(
        normalized_payload.get("source_updated_at")
    )
    # Payload may carry compatibility source key for API compatibility, but persistence
    # uses source_id only. Overwriting source_id on existing rows is intentional: it
    # self-heals any row with an incorrect owner reference.
    normalized_payload.pop("description_html", None)
    normalized_payload.pop("raw_payload", None)
    drop_legacy_job_payload_fields(normalized_payload, include_source=True)
    for key, value in normalized_payload.items():
        setattr(job, key, value)
    job.status = JobStatus.open
    job.last_seen_at = sync_started_at
    job.updated_at = sync_started_at
