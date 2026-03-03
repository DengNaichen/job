"""Unit tests for the job blob backfill script."""

from __future__ import annotations

import json

import pytest
import sqlalchemy as sa
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job
from app.services.application.blob.job_blob import JobBlobManager
from app.services.infra.blob_storage import BlobStorageError
from scripts.migrate_job_blobs_to_storage import migrate_job_blobs


class _InMemoryBlobStorage:
    def __init__(self, *, fail_prefix: str | None = None):
        self.fail_prefix = fail_prefix
        self.objects: dict[str, bytes] = {}

    @property
    def is_enabled(self) -> bool:
        return True

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        _ = (content_type, content_encoding)
        if self.fail_prefix and key.startswith(self.fail_prefix):
            raise BlobStorageError("storage boom")
        already_exists = key in self.objects
        self.objects.setdefault(key, data)
        return not already_exists

    async def download(self, *, key: str) -> bytes:
        return self.objects[key]


def _build_job(
    *,
    job_id: str = "job-1",
) -> Job:
    return Job(
        id=job_id,
        source_id="source-1",
        external_job_id=f"ext-{job_id}",
        title="Engineer",
        apply_url=f"https://example.com/jobs/{job_id}",
    )


async def _persist_job(session: AsyncSession, job: Job) -> Job:
    session.add(job)
    await session.commit()
    return job


async def _ensure_legacy_blob_columns(session: AsyncSession) -> None:
    result = await session.exec(sa.text("PRAGMA table_info(job)"))
    existing = {row[1] for row in result.all()}
    if "description_html" not in existing:
        await session.exec(sa.text("ALTER TABLE job ADD COLUMN description_html TEXT"))
    if "raw_payload" not in existing:
        await session.exec(sa.text("ALTER TABLE job ADD COLUMN raw_payload JSON"))
    await session.commit()


async def _set_legacy_blob_columns(
    session: AsyncSession,
    *,
    job_id: str,
    description_html: str | None,
    raw_payload: dict | None,
    description_html_key: str | None = None,
    raw_payload_key: str | None = None,
) -> None:
    await _ensure_legacy_blob_columns(session)
    await session.exec(
        sa.text(
            """
            UPDATE job
            SET description_html = :description_html,
                raw_payload = :raw_payload,
                description_html_key = :description_html_key,
                raw_payload_key = :raw_payload_key
            WHERE id = :job_id
            """
        ),
        params={
            "description_html": description_html,
            "raw_payload": json.dumps({} if raw_payload is None else raw_payload),
            "description_html_key": description_html_key,
            "raw_payload_key": raw_payload_key,
            "job_id": job_id,
        },
    )
    await session.commit()


async def _fetch_job_row(session: AsyncSession, job_id: str) -> dict:
    result = await session.exec(
        sa.text(
            """
            SELECT
                id,
                description_plain,
                description_html_key,
                description_html_hash,
                raw_payload_key,
                raw_payload_hash
            FROM job
            WHERE id = :job_id
            """
        ),
        params={"job_id": job_id},
    )
    row = result.mappings().one()
    return dict(row)


@pytest.mark.asyncio
async def test_migrate_job_blobs_dry_run_does_not_write_db(session: AsyncSession) -> None:
    await _persist_job(session, _build_job(job_id="job-1"))
    await _set_legacy_blob_columns(
        session,
        job_id="job-1",
        description_html="<p>Hello</p>",
        raw_payload={"id": "123"},
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        dry_run=True,
    )

    job_row = await _fetch_job_row(session, "job-1")
    assert stats.scanned_count == 1
    assert stats.planned_upload_count == 2
    assert stats.upload_count == 0
    assert job_row["description_html_key"] is None
    assert job_row["raw_payload_key"] is None
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_migrate_job_blobs_skips_rows_with_existing_key(session: AsyncSession) -> None:
    await _persist_job(session, _build_job(job_id="job-2"))
    await _set_legacy_blob_columns(
        session,
        job_id="job-2",
        description_html="<p>Hello</p>",
        raw_payload={},
        description_html_key="job-html/existing.html.gz",
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        migrate_html=True,
        migrate_raw=False,
    )

    assert stats.scanned_count == 1
    assert stats.skip_count == 1
    assert stats.upload_count == 0
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_migrate_job_blobs_uploads_and_updates_db(session: AsyncSession) -> None:
    await _persist_job(session, _build_job(job_id="job-3"))
    await _set_legacy_blob_columns(
        session,
        job_id="job-3",
        description_html="<p>Hello</p>",
        raw_payload={"id": "123"},
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
    )

    job_row = await _fetch_job_row(session, "job-3")
    assert stats.upload_count == 2
    assert stats.updated_job_count == 1
    assert job_row["description_html_key"] is not None
    assert job_row["description_html_hash"] is not None
    assert job_row["raw_payload_key"] is not None
    assert job_row["raw_payload_hash"] is not None
    assert set(storage.objects) == {
        job_row["description_html_key"],
        job_row["raw_payload_key"],
    }


@pytest.mark.asyncio
async def test_migrate_job_blobs_storage_failure_does_not_write_bad_pointer(
    session: AsyncSession,
) -> None:
    await _persist_job(session, _build_job(job_id="job-4"))
    await _set_legacy_blob_columns(
        session,
        job_id="job-4",
        description_html="<p>Hello</p>",
        raw_payload={},
    )
    storage = _InMemoryBlobStorage(fail_prefix="job-html/")

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        migrate_html=True,
        migrate_raw=False,
    )

    job_row = await _fetch_job_row(session, "job-4")
    assert stats.failure_count == 1
    assert job_row["description_html_key"] is None
    assert job_row["description_html_hash"] is None


@pytest.mark.asyncio
async def test_migrate_job_blobs_backfills_description_plain_from_html(
    session: AsyncSession,
) -> None:
    await _persist_job(session, _build_job(job_id="job-5"))
    await _set_legacy_blob_columns(
        session,
        job_id="job-5",
        description_html="<p>Hello <strong>world</strong></p>",
        raw_payload=None,
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        migrate_html=True,
        migrate_raw=False,
    )

    job_row = await _fetch_job_row(session, "job-5")
    assert stats.description_plain_backfilled_count == 1
    assert isinstance(job_row["description_plain"], str)
    assert "Hello world" in job_row["description_plain"]
