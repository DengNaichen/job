#!/usr/bin/env python3
"""Backfill job blob pointers from legacy inline columns into object storage.

This script is intended to run before dropping legacy `job.description_html`
and `job.raw_payload` columns.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.services.application.blob.job_blob import JobBlobManager, JobBlobPointers, JobBlobSyncResult
from app.services.infra.blob_storage import build_description_html_blob, build_raw_payload_blob
from app.services.infra.text import html_to_text

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_JOB_TABLE = sa.table(
    "job",
    sa.column("id", sa.String()),
    sa.column("description_plain", sa.Text()),
    sa.column("description_html", sa.Text()),
    sa.column("description_html_key", sa.String(length=255)),
    sa.column("description_html_hash", sa.String(length=64)),
    sa.column("raw_payload", sa.JSON()),
    sa.column("raw_payload_key", sa.String(length=255)),
    sa.column("raw_payload_hash", sa.String(length=64)),
)


@dataclass
class BlobMigrationStats:
    scanned_count: int = 0
    upload_count: int = 0
    planned_upload_count: int = 0
    skip_count: int = 0
    updated_job_count: int = 0
    description_plain_backfilled_count: int = 0
    planned_description_plain_backfill_count: int = 0
    failure_count: int = 0


@dataclass
class _JobBlobRow:
    id: str
    description_plain: str | None
    description_html: str | None
    description_html_key: str | None
    description_html_hash: str | None
    raw_payload: Any
    raw_payload_key: str | None
    raw_payload_hash: str | None


@dataclass
class _JobBlobProxy:
    description_html_key: str | None
    description_html_hash: str | None
    raw_payload_key: str | None
    raw_payload_hash: str | None

    @classmethod
    def from_row(cls, row: _JobBlobRow) -> _JobBlobProxy:
        return cls(
            description_html_key=row.description_html_key,
            description_html_hash=row.description_html_hash,
            raw_payload_key=row.raw_payload_key,
            raw_payload_hash=row.raw_payload_hash,
        )

    def as_existing_pointers(self) -> JobBlobPointers:
        return JobBlobPointers(
            description_html_key=self.description_html_key,
            description_html_hash=self.description_html_hash,
            raw_payload_key=self.raw_payload_key,
            raw_payload_hash=self.raw_payload_hash,
        )


def _to_blob_row(mapping: sa.RowMapping) -> _JobBlobRow:
    return _JobBlobRow(
        id=str(mapping["id"]),
        description_plain=mapping["description_plain"],
        description_html=mapping["description_html"],
        description_html_key=mapping["description_html_key"],
        description_html_hash=mapping["description_html_hash"],
        raw_payload=mapping["raw_payload"],
        raw_payload_key=mapping["raw_payload_key"],
        raw_payload_hash=mapping["raw_payload_hash"],
    )


def _fields_to_sync(
    row: _JobBlobRow,
    *,
    migrate_html: bool,
    migrate_raw: bool,
) -> tuple[set[str], int]:
    fields: set[str] = set()
    skip_count = 0

    if migrate_html:
        if build_description_html_blob(row.description_html) is None:
            skip_count += 1
        elif row.description_html_key:
            skip_count += 1
        else:
            fields.add("description_html")

    if migrate_raw:
        if build_raw_payload_blob(row.raw_payload) is None:
            skip_count += 1
        elif row.raw_payload_key:
            skip_count += 1
        else:
            fields.add("raw_payload")

    return fields, skip_count


def _needs_description_plain_backfill(row: _JobBlobRow) -> bool:
    has_plain = isinstance(row.description_plain, str) and row.description_plain.strip() != ""
    has_html = build_description_html_blob(row.description_html) is not None
    return (not has_plain) and has_html


def _backfilled_description_plain(row: _JobBlobRow) -> str | None:
    if not _needs_description_plain_backfill(row):
        return None
    if row.description_html is None:
        return None
    text = html_to_text(row.description_html).strip()
    return text or None


async def _fetch_batch(
    session: AsyncSession,
    *,
    last_id: str | None,
    batch_size: int,
) -> list[_JobBlobRow]:
    statement = (
        sa.select(
            _JOB_TABLE.c.id,
            _JOB_TABLE.c.description_plain,
            _JOB_TABLE.c.description_html,
            _JOB_TABLE.c.description_html_key,
            _JOB_TABLE.c.description_html_hash,
            _JOB_TABLE.c.raw_payload,
            _JOB_TABLE.c.raw_payload_key,
            _JOB_TABLE.c.raw_payload_hash,
        )
        .order_by(_JOB_TABLE.c.id)
        .limit(batch_size)
    )
    if last_id is not None:
        statement = statement.where(_JOB_TABLE.c.id > last_id)
    result = await session.exec(statement)
    return [_to_blob_row(row) for row in result.mappings().all()]


async def _assert_required_columns_exist(session: AsyncSession) -> None:
    bind = session.get_bind()
    if bind is None:
        raise RuntimeError("Unable to inspect database: missing bind on session")
    columns = await session.run_sync(
        lambda sync_session: {
            col["name"]
            for col in sa.inspect(sync_session.connection()).get_columns("job")
        }
    )
    required = {
        "id",
        "description_plain",
        "description_html",
        "description_html_key",
        "description_html_hash",
        "raw_payload",
        "raw_payload_key",
        "raw_payload_hash",
    }
    missing = sorted(required - columns)
    if missing:
        raise RuntimeError(
            "job table is missing columns required for blob migration: "
            + ", ".join(missing)
            + ". Run this script before dropping legacy blob columns."
        )


async def migrate_job_blobs(
    session: AsyncSession,
    blob_manager: JobBlobManager,
    *,
    batch_size: int = 100,
    dry_run: bool = False,
    migrate_html: bool = True,
    migrate_raw: bool = True,
    backfill_description_plain: bool = True,
) -> BlobMigrationStats:
    """Backfill missing blob pointers for existing jobs."""
    if not migrate_html and not migrate_raw:
        raise ValueError("At least one of migrate_html or migrate_raw must be enabled")
    if batch_size <= 0:
        raise ValueError("batch_size must be > 0")

    await _assert_required_columns_exist(session)
    blob_manager.assert_available()

    stats = BlobMigrationStats()
    last_id: str | None = None

    while True:
        rows = await _fetch_batch(session, last_id=last_id, batch_size=batch_size)
        if not rows:
            break

        for row in rows:
            last_id = row.id
            stats.scanned_count += 1

            fields_to_sync, skip_count = _fields_to_sync(
                row,
                migrate_html=migrate_html,
                migrate_raw=migrate_raw,
            )
            stats.skip_count += skip_count

            plain_needs_backfill = backfill_description_plain and _needs_description_plain_backfill(row)
            backfilled_plain = _backfilled_description_plain(row) if plain_needs_backfill else None

            if dry_run:
                stats.planned_upload_count += len(fields_to_sync)
                if plain_needs_backfill:
                    stats.planned_description_plain_backfill_count += 1
                continue

            sync_result = JobBlobSyncResult()
            proxy = _JobBlobProxy.from_row(row)
            if fields_to_sync:
                sync_kwargs: dict[str, object] = {}
                if "description_html" in fields_to_sync:
                    sync_kwargs["description_html"] = row.description_html
                if "raw_payload" in fields_to_sync:
                    sync_kwargs["raw_payload"] = row.raw_payload
                try:
                    sync_result = await blob_manager.sync_job_blobs(
                        proxy,  # type: ignore[arg-type]
                        existing_pointers=proxy.as_existing_pointers(),
                        explicit_fields=fields_to_sync,
                        **sync_kwargs,
                    )
                except Exception:
                    stats.failure_count += 1
                    logger.exception("Blob migration failed for job_id=%s", row.id)
                    continue

            update_values: dict[str, object] = {}
            if sync_result.updated_count:
                update_values.update(
                    {
                        "description_html_key": proxy.description_html_key,
                        "description_html_hash": proxy.description_html_hash,
                        "raw_payload_key": proxy.raw_payload_key,
                        "raw_payload_hash": proxy.raw_payload_hash,
                    }
                )
            if plain_needs_backfill:
                update_values["description_plain"] = backfilled_plain

            if not update_values:
                stats.upload_count += sync_result.upload_count
                continue

            try:
                await session.exec(
                    sa.update(_JOB_TABLE).where(_JOB_TABLE.c.id == row.id).values(**update_values)
                )
            except Exception:
                stats.failure_count += 1
                logger.exception("DB update failed for job_id=%s", row.id)
                continue

            stats.updated_job_count += 1
            stats.upload_count += sync_result.upload_count
            if plain_needs_backfill:
                stats.description_plain_backfilled_count += 1

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
    parser.add_argument(
        "--skip-description-plain-backfill",
        action="store_true",
        help="Do not backfill description_plain from description_html",
    )
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
            backfill_description_plain=not args.skip_description_plain_backfill,
        )

    logger.info(
        "Blob migration complete scanned=%s uploaded=%s planned=%s skipped=%s failed=%s "
        "updated_jobs=%s plain_backfilled=%s planned_plain_backfill=%s",
        stats.scanned_count,
        stats.upload_count,
        stats.planned_upload_count,
        stats.skip_count,
        stats.failure_count,
        stats.updated_job_count,
        stats.description_plain_backfilled_count,
        stats.planned_description_plain_backfill_count,
    )
    return stats


def main() -> None:
    asyncio.run(run(parse_args()))


if __name__ == "__main__":
    main()
