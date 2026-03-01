"""Unit tests for the job blob backfill script."""

from __future__ import annotations

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job
from app.services.blob_storage import BlobStorageError, JobBlobManager
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
    description_html: str | None = "<p>Hello</p>",
    raw_payload: dict | None = None,
    description_html_key: str | None = None,
    raw_payload_key: str | None = None,
) -> Job:
    return Job(
        id=job_id,
        source="greenhouse:acme",
        external_job_id=f"ext-{job_id}",
        title="Engineer",
        apply_url=f"https://example.com/jobs/{job_id}",
        description_html=description_html,
        description_html_key=description_html_key,
        raw_payload={} if raw_payload is None else raw_payload,
        raw_payload_key=raw_payload_key,
    )


async def _persist_job(session: AsyncSession, job: Job) -> Job:
    session.add(job)
    await session.commit()
    return job


async def _fetch_job(session: AsyncSession, job_id: str) -> Job:
    result = await session.exec(select(Job).where(Job.id == job_id))
    return result.one()


@pytest.mark.asyncio
async def test_migrate_job_blobs_dry_run_does_not_write_db(session: AsyncSession) -> None:
    await _persist_job(
        session,
        _build_job(job_id="job-1", description_html="<p>Hello</p>", raw_payload={"id": "123"}),
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        dry_run=True,
    )

    job = await _fetch_job(session, "job-1")
    assert stats.scanned_count == 1
    assert stats.planned_upload_count == 2
    assert stats.upload_count == 0
    assert job.description_html_key is None
    assert job.raw_payload_key is None
    assert storage.objects == {}


@pytest.mark.asyncio
async def test_migrate_job_blobs_skips_rows_with_existing_key(session: AsyncSession) -> None:
    await _persist_job(
        session,
        _build_job(
            job_id="job-2",
            description_html="<p>Hello</p>",
            description_html_key="job-html/existing.html.gz",
        ),
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
    await _persist_job(
        session,
        _build_job(job_id="job-3", description_html="<p>Hello</p>", raw_payload={"id": "123"}),
    )
    storage = _InMemoryBlobStorage()

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
    )

    job = await _fetch_job(session, "job-3")
    assert stats.upload_count == 2
    assert stats.updated_job_count == 1
    assert job.description_html_key is not None
    assert job.description_html_hash is not None
    assert job.raw_payload_key is not None
    assert job.raw_payload_hash is not None
    assert set(storage.objects) == {job.description_html_key, job.raw_payload_key}


@pytest.mark.asyncio
async def test_migrate_job_blobs_storage_failure_does_not_write_bad_pointer(
    session: AsyncSession,
) -> None:
    await _persist_job(
        session,
        _build_job(job_id="job-4", description_html="<p>Hello</p>", raw_payload={}),
    )
    storage = _InMemoryBlobStorage(fail_prefix="job-html/")

    stats = await migrate_job_blobs(
        session,
        JobBlobManager(storage),
        batch_size=10,
        migrate_html=True,
        migrate_raw=False,
    )

    job = await _fetch_job(session, "job-4")
    assert stats.failure_count == 1
    assert job.description_html_key is None
    assert job.description_html_hash is None
