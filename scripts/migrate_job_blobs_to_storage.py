#!/usr/bin/env python3
"""Backfill large job blobs from Postgres columns into object storage."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import select

from app.core.config import get_settings
from app.models import Job
from app.services.application.job_blob import JobBlobManager, JobBlobPointers
from app.services.infra.blob_storage import build_description_html_blob, build_raw_payload_blob

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class BlobMigrationStats:
    scanned_count: int = 0
    upload_count: int = 0
    planned_upload_count: int = 0
    skip_count: int = 0
    updated_job_count: int = 0
    failure_count: int = 0


def _restore_blob_pointers(job: Job, pointers: JobBlobPointers) -> None:
    job.description_html_key = pointers.description_html_key
    job.description_html_hash = pointers.description_html_hash
    job.raw_payload_key = pointers.raw_payload_key
    job.raw_payload_hash = pointers.raw_payload_hash


def _fields_to_sync(
    job: Job,
    *,
    migrate_html: bool,
    migrate_raw: bool,
) -> tuple[set[str], int]:
    fields: set[str] = set()
    skip_count = 0

    if migrate_html:
        if build_description_html_blob(job.description_html) is None:
            skip_count += 1
        elif job.description_html_key:
            skip_count += 1
        else:
            fields.add("description_html")

    if migrate_raw:
        if build_raw_payload_blob(job.raw_payload) is None:
            skip_count += 1
        elif job.raw_payload_key:
            skip_count += 1
        else:
            fields.add("raw_payload")

    return fields, skip_count


async def _fetch_batch(
    session: AsyncSession,
    *,
    last_id: str | None,
    batch_size: int,
) -> list[Job]:
    statement = select(Job).order_by(Job.id).limit(batch_size)
    if last_id is not None:
        statement = statement.where(Job.id > last_id)
    result = await session.exec(statement)
    return list(result.all())


async def migrate_job_blobs(
    session: AsyncSession,
    blob_manager: JobBlobManager,
    *,
    batch_size: int = 100,
    dry_run: bool = False,
    migrate_html: bool = True,
    migrate_raw: bool = True,
) -> BlobMigrationStats:
    """Backfill missing blob pointers for existing jobs."""
    if not migrate_html and not migrate_raw:
        raise ValueError("At least one of migrate_html or migrate_raw must be enabled")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    blob_manager.assert_available()
    stats = BlobMigrationStats()
    last_id: str | None = None

    while True:
        jobs = await _fetch_batch(session, last_id=last_id, batch_size=batch_size)
        if not jobs:
            break

        for job in jobs:
            last_id = str(job.id)
            stats.scanned_count += 1

            fields_to_sync, skip_count = _fields_to_sync(
                job,
                migrate_html=migrate_html,
                migrate_raw=migrate_raw,
            )
            stats.skip_count += skip_count
            if not fields_to_sync:
                continue

            if dry_run:
                stats.planned_upload_count += len(fields_to_sync)
                continue

            existing_pointers = JobBlobPointers.from_job(job)
            try:
                result = await blob_manager.sync_job_blobs(
                    job,
                    existing_pointers=existing_pointers,
                    explicit_fields=fields_to_sync,
                )
            except Exception:
                _restore_blob_pointers(job, existing_pointers)
                stats.failure_count += 1
                logger.exception("Blob migration failed for job_id=%s", job.id)
                continue

            if result.updated_count:
                session.add(job)
                stats.updated_job_count += 1
            stats.upload_count += result.upload_count

        if not dry_run:
            await session.commit()

    if dry_run:
        await session.rollback()

    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill job HTML/raw blobs into storage")
    parser.add_argument(
        "--batch-size", type=int, default=100, help="Number of jobs scanned per batch"
    )
    parser.add_argument("--dry-run", action="store_true", help="Only report what would be uploaded")
    parser.add_argument("--html-only", action="store_true", help="Only migrate description_html")
    parser.add_argument("--raw-only", action="store_true", help="Only migrate raw_payload")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> BlobMigrationStats:
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=settings.debug)
    blob_manager = JobBlobManager()

    migrate_html = not args.raw_only
    migrate_raw = not args.html_only

    async with AsyncSession(engine) as session:
        stats = await migrate_job_blobs(
            session,
            blob_manager,
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            migrate_html=migrate_html,
            migrate_raw=migrate_raw,
        )

    logger.info(
        "Blob migration complete scanned=%s uploaded=%s planned=%s skipped=%s failed=%s updated_jobs=%s",
        stats.scanned_count,
        stats.upload_count,
        stats.planned_upload_count,
        stats.skip_count,
        stats.failure_count,
        stats.updated_job_count,
    )
    return stats


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
