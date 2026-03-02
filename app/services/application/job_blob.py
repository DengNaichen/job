"""Application service for managing job blobs.

This separates the domain/application layer logic (which knows about the Job model
and pointers) from the pure infrastructure layer logic (which only knows about bytes).
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Any

from app.models import Job
from app.services.infra.blob_storage import (
    build_description_html_blob,
    build_raw_payload_blob,
)
from app.services.infra.blob_storage import (
    BlobStorageClient,
    BlobStorageNotConfiguredError,
    create_blob_storage,
)


@dataclass(frozen=True)
class JobBlobPointers:
    """Persisted blob pointer state for one job row."""

    description_html_key: str | None = None
    description_html_hash: str | None = None
    raw_payload_key: str | None = None
    raw_payload_hash: str | None = None

    @classmethod
    def from_job(cls, job: Job | None) -> JobBlobPointers:
        if job is None:
            return cls()
        return cls(
            description_html_key=job.description_html_key,
            description_html_hash=job.description_html_hash,
            raw_payload_key=job.raw_payload_key,
            raw_payload_hash=job.raw_payload_hash,
        )


@dataclass(frozen=True)
class JobBlobSyncResult:
    """Describes what changed during one blob sync."""

    description_html_uploaded: bool = False
    description_html_updated: bool = False
    raw_payload_uploaded: bool = False
    raw_payload_updated: bool = False

    @property
    def upload_count(self) -> int:
        return int(self.description_html_uploaded) + int(self.raw_payload_uploaded)

    @property
    def updated_count(self) -> int:
        return int(self.description_html_updated) + int(self.raw_payload_updated)


class JobBlobManager:
    """Manage large job fields stored in blob storage."""

    def __init__(self, storage: BlobStorageClient | None = None):
        self.storage = storage or create_blob_storage()

    def assert_available(self) -> None:
        """Fail fast for scripts that require storage."""
        if not self.storage.is_enabled:
            reason = getattr(
                self.storage,
                "reason",
                "Blob storage is required for this operation but is not configured.",
            )
            raise BlobStorageNotConfiguredError(str(reason))

    async def sync_job_blobs(
        self,
        job: Job,
        *,
        existing_pointers: JobBlobPointers | None = None,
        explicit_fields: set[str] | None = None,
    ) -> JobBlobSyncResult:
        """Upload changed job blobs first, then update DB pointers on the model."""
        import asyncio

        existing_pointers = existing_pointers or JobBlobPointers()

        needs_html = explicit_fields is None or "description_html" in explicit_fields
        needs_raw = explicit_fields is None or "raw_payload" in explicit_fields

        html_coro = (
            self._sync_html_blob(job, existing_pointers=existing_pointers)
            if needs_html
            else self._mock_sync_result()
        )
        raw_coro = (
            self._sync_raw_payload_blob(job, existing_pointers=existing_pointers)
            if needs_raw
            else self._mock_sync_result()
        )

        (html_uploaded, html_updated), (raw_uploaded, raw_updated) = await asyncio.gather(
            html_coro, raw_coro
        )

        return JobBlobSyncResult(
            description_html_uploaded=html_uploaded,
            description_html_updated=html_updated,
            raw_payload_uploaded=raw_uploaded,
            raw_payload_updated=raw_updated,
        )

    async def _mock_sync_result(self) -> tuple[bool, bool]:
        return False, False

    async def sync_many_job_blobs(
        self,
        jobs: list[Job],
        *,
        max_concurrent: int = 20,
    ) -> list[JobBlobSyncResult]:
        """Batch concurrent sync with semaphore protection to avoid rate limiting."""
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _sync_with_semaphore(job: Job) -> JobBlobSyncResult:
            async with semaphore:
                return await self.sync_job_blobs(job)

        tasks = [_sync_with_semaphore(job) for job in jobs]
        return await asyncio.gather(*tasks)

    async def load_description_html(self, job: Job) -> str | None:
        """Return HTML from the DB column first, then storage if needed."""
        if job.description_html:
            return job.description_html
        if not job.description_html_key:
            return None
        raw_bytes = await self.storage.download(key=job.description_html_key)
        return gzip.decompress(raw_bytes).decode("utf-8")

    async def load_raw_payload(self, job: Job) -> Any:
        """Return raw payload from the DB column first, then storage if needed."""
        if job.raw_payload not in (None, {}, []):
            return job.raw_payload
        if not job.raw_payload_key:
            return None
        raw_bytes = await self.storage.download(key=job.raw_payload_key)
        return json.loads(gzip.decompress(raw_bytes).decode("utf-8"))

    async def _sync_html_blob(
        self,
        job: Job,
        *,
        existing_pointers: JobBlobPointers,
    ) -> tuple[bool, bool]:
        prepared = build_description_html_blob(job.description_html)
        if prepared is None:
            updated = (
                existing_pointers.description_html_key is not None
                or existing_pointers.description_html_hash is not None
            )
            job.description_html_key = None
            job.description_html_hash = None
            return False, updated

        if (
            existing_pointers.description_html_hash == prepared.sha256
            and existing_pointers.description_html_key
        ):
            job.description_html_key = existing_pointers.description_html_key
            job.description_html_hash = existing_pointers.description_html_hash
            return False, False

        uploaded = await self.storage.upload_if_missing(
            key=prepared.key,
            data=prepared.data,
            content_type=prepared.content_type,
        )
        updated = (
            existing_pointers.description_html_key != prepared.key
            or existing_pointers.description_html_hash != prepared.sha256
        )
        job.description_html_key = prepared.key
        job.description_html_hash = prepared.sha256
        return uploaded, updated

    async def _sync_raw_payload_blob(
        self,
        job: Job,
        *,
        existing_pointers: JobBlobPointers,
    ) -> tuple[bool, bool]:
        prepared = build_raw_payload_blob(job.raw_payload)
        if prepared is None:
            updated = (
                existing_pointers.raw_payload_key is not None
                or existing_pointers.raw_payload_hash is not None
            )
            job.raw_payload_key = None
            job.raw_payload_hash = None
            return False, updated

        if (
            existing_pointers.raw_payload_hash == prepared.sha256
            and existing_pointers.raw_payload_key
        ):
            job.raw_payload_key = existing_pointers.raw_payload_key
            job.raw_payload_hash = existing_pointers.raw_payload_hash
            return False, False

        uploaded = await self.storage.upload_if_missing(
            key=prepared.key,
            data=prepared.data,
            content_type=prepared.content_type,
        )
        updated = (
            existing_pointers.raw_payload_key != prepared.key
            or existing_pointers.raw_payload_hash != prepared.sha256
        )
        job.raw_payload_key = prepared.key
        job.raw_payload_hash = prepared.sha256
        return uploaded, updated
