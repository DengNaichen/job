"""Blob storage helpers for large job fields.

Storage uploads happen before the database commit so the database never points
at a missing object. If the later database transaction rolls back, the uploaded
blob becomes an orphan. That tradeoff is acceptable because orphaned blobs are
repairable, while a database pointer to a missing blob would break reads.
"""

from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings, get_settings
from app.models import Job


HTML_BLOB_PREFIX = "job-html"
RAW_BLOB_PREFIX = "job-raw"


class BlobStorageError(RuntimeError):
    """Base exception for blob storage failures."""


class BlobStorageNotConfiguredError(BlobStorageError):
    """Raised when blob storage is required but not configured."""


class BlobNotFoundError(BlobStorageError):
    """Raised when a configured blob key cannot be fetched."""


@dataclass(frozen=True)
class PreparedBlob:
    """Prepared blob bytes plus its storage metadata."""

    key: str
    sha256: str
    content_type: str
    data: bytes


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


class BlobStorageClient(Protocol):
    """Interface for blob storage backends."""

    @property
    def is_enabled(self) -> bool:
        """Whether the backend is usable for read/write calls."""

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        """Upload a blob if the object key does not already exist."""

    async def download(self, *, key: str) -> bytes:
        """Download the stored bytes for one object key."""


def compute_sha256_hex(data: bytes) -> str:
    """Return a stable content hash for raw bytes."""
    return hashlib.sha256(data).hexdigest()


def gzip_bytes(data: bytes) -> bytes:
    """Compress bytes deterministically for stable tests and storage writes."""
    return gzip.compress(data, mtime=0)


def serialize_raw_payload(raw_payload: Any) -> bytes | None:
    """Serialize raw payload JSON deterministically."""
    if raw_payload in (None, {}, []):
        return None
    return json.dumps(
        raw_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def build_description_html_blob(description_html: str | None) -> PreparedBlob | None:
    """Build the storage payload for description HTML."""
    if description_html is None or not description_html.strip():
        return None
    raw_bytes = description_html.encode("utf-8")
    sha256 = compute_sha256_hex(raw_bytes)
    return PreparedBlob(
        key=f"{HTML_BLOB_PREFIX}/{sha256}.html.gz",
        sha256=sha256,
        content_type="text/html; charset=utf-8",
        data=gzip_bytes(raw_bytes),
    )


def build_raw_payload_blob(raw_payload: Any) -> PreparedBlob | None:
    """Build the storage payload for raw source payloads."""
    raw_bytes = serialize_raw_payload(raw_payload)
    if raw_bytes is None:
        return None
    sha256 = compute_sha256_hex(raw_bytes)
    return PreparedBlob(
        key=f"{RAW_BLOB_PREFIX}/{sha256}.json.gz",
        sha256=sha256,
        content_type="application/json",
        data=gzip_bytes(raw_bytes),
    )


class DisabledBlobStorage:
    """Placeholder backend that explains why storage is unavailable."""

    def __init__(self, *, reason: str):
        self.reason = reason

    @property
    def is_enabled(self) -> bool:
        return False

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        _ = (key, data, content_type, content_encoding)
        raise BlobStorageNotConfiguredError(self.reason)

    async def download(self, *, key: str) -> bytes:
        _ = key
        raise BlobStorageNotConfiguredError(self.reason)


class SupabaseBlobStorage:
    """Supabase Storage backend via the REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        bucket: str,
        service_key: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.bucket = bucket
        self.service_key = service_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._known_existing_keys: set[str] = set()
        self.max_retries = 3

    @property
    def is_enabled(self) -> bool:
        return True

    def _auth_headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.service_key}",
            "apikey": self.service_key,
        }

    def _quoted_key(self, key: str) -> str:
        return quote(key.lstrip("/"), safe="/")

    def _info_url(self, key: str) -> str:
        return f"{self.base_url}/object/info/{self.bucket}/{self._quoted_key(key)}"

    def _upload_url(self, key: str) -> str:
        return f"{self.base_url}/object/{self.bucket}/{self._quoted_key(key)}"

    def _download_url(self, key: str) -> str:
        return f"{self.base_url}/object/authenticated/{self.bucket}/{self._quoted_key(key)}"

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self.timeout_seconds, transport=self.transport)

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        content: bytes | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    content=content,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(0.5 * attempt)
                continue

            if response.status_code >= 500 and attempt < self.max_retries:
                await asyncio.sleep(0.5 * attempt)
                continue
            return response

        if last_error is not None:
            raise BlobStorageError(
                f"Supabase storage request failed for {url}: {last_error}"
            ) from last_error
        raise BlobStorageError(
            f"Supabase storage request failed for {url} after {self.max_retries} attempts"
        )

    @staticmethod
    def _is_missing_object_response(response: httpx.Response) -> bool:
        if response.status_code == 404:
            return True
        if response.status_code != 400:
            return False
        try:
            payload = response.json()
        except ValueError:
            return False
        error_value = str(payload.get("error") or "").strip().lower()
        message_value = str(payload.get("message") or "").strip().lower()
        return error_value == "not_found" and "object not found" in message_value

    async def upload_if_missing(
        self,
        *,
        key: str,
        data: bytes,
        content_type: str,
        content_encoding: str = "gzip",
    ) -> bool:
        if key in self._known_existing_keys:
            return False

        async with self._client() as client:
            info_response = await self._request_with_retry(
                client,
                "GET",
                self._info_url(key),
                headers=self._auth_headers(),
            )
            if info_response.status_code == 200:
                self._known_existing_keys.add(key)
                return False
            if not self._is_missing_object_response(info_response):
                raise BlobStorageError(
                    f"Supabase storage info lookup failed for {key}: "
                    f"{info_response.status_code} {info_response.text}"
                )

            upload_headers = {
                **self._auth_headers(),
                "content-type": content_type,
                "content-encoding": content_encoding,
                "x-upsert": "false",
            }
            upload_response = await self._request_with_retry(
                client,
                "POST",
                self._upload_url(key),
                headers=upload_headers,
                content=data,
            )
            if upload_response.status_code in {200, 201}:
                self._known_existing_keys.add(key)
                return True

            response_text = upload_response.text.lower()
            if upload_response.status_code in {400, 409} and "exist" in response_text:
                self._known_existing_keys.add(key)
                return False

            raise BlobStorageError(
                f"Supabase storage upload failed for {key}: "
                f"{upload_response.status_code} {upload_response.text}"
            )

    async def download(self, *, key: str) -> bytes:
        async with self._client() as client:
            response = await self._request_with_retry(
                client,
                "GET",
                self._download_url(key),
                headers=self._auth_headers(),
            )
        if response.status_code == 404:
            raise BlobNotFoundError(f"Blob not found: {key}")
        if response.status_code != 200:
            raise BlobStorageError(
                f"Supabase storage download failed for {key}: "
                f"{response.status_code} {response.text}"
            )
        self._known_existing_keys.add(key)
        return response.content


def create_blob_storage(
    settings: Settings | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> BlobStorageClient:
    """Create the configured blob storage backend."""
    settings = settings or get_settings()
    provider = settings.storage_provider.strip().lower()

    if provider in {"", "none", "disabled"}:
        return DisabledBlobStorage(
            reason="Blob storage is disabled. Set STORAGE_PROVIDER=supabase to enable it.",
        )

    if provider != "supabase":
        return DisabledBlobStorage(
            reason=f"Unsupported storage provider: {settings.storage_provider}",
        )

    missing = []
    if not settings.supabase_storage_base_url:
        missing.append("SUPABASE_STORAGE_BASE_URL")
    if not settings.supabase_storage_bucket:
        missing.append("SUPABASE_STORAGE_BUCKET")
    if not settings.supabase_storage_service_key:
        missing.append("SUPABASE_STORAGE_SERVICE_KEY")
    if missing:
        return DisabledBlobStorage(
            reason="Supabase Storage is not fully configured. Missing: " + ", ".join(missing),
        )

    return SupabaseBlobStorage(
        base_url=settings.supabase_storage_base_url,
        bucket=settings.supabase_storage_bucket,
        service_key=settings.supabase_storage_service_key,
        timeout_seconds=settings.storage_timeout_seconds,
        transport=transport,
    )


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
        existing_pointers = existing_pointers or JobBlobPointers()
        description_html_uploaded = False
        description_html_updated = False
        raw_payload_uploaded = False
        raw_payload_updated = False

        if explicit_fields is None or "description_html" in explicit_fields:
            description_html_uploaded, description_html_updated = await self._sync_html_blob(
                job,
                existing_pointers=existing_pointers,
            )

        if explicit_fields is None or "raw_payload" in explicit_fields:
            raw_payload_uploaded, raw_payload_updated = await self._sync_raw_payload_blob(
                job,
                existing_pointers=existing_pointers,
            )

        return JobBlobSyncResult(
            description_html_uploaded=description_html_uploaded,
            description_html_updated=description_html_updated,
            raw_payload_uploaded=raw_payload_uploaded,
            raw_payload_updated=raw_payload_updated,
        )

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
