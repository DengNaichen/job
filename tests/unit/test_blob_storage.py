"""Unit tests for blob storage helpers."""

from __future__ import annotations

import gzip
import httpx
import pytest

from app.models import Job
from app.services.application.job_blob import JobBlobManager, JobBlobPointers
from app.services.infra.blob_storage import (
    build_description_html_blob,
    build_raw_payload_blob,
    compute_sha256_hex,
)
from app.services.infra.blob_storage import SupabaseBlobStorage


class _InMemoryBlobStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.upload_calls: list[str] = []

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
        self.upload_calls.append(key)
        already_exists = key in self.objects
        self.objects.setdefault(key, data)
        return not already_exists

    async def download(self, *, key: str) -> bytes:
        return self.objects[key]


def _build_job() -> Job:
    return Job(
        id="job-1",
        source="greenhouse:acme",
        external_job_id="123",
        title="Engineer",
        apply_url="https://example.com/jobs/123",
        description_html="<p>Hello</p>",
        raw_payload={"b": 2, "a": 1},
    )


def test_build_description_html_blob_uses_sha256_key_and_gzip() -> None:
    blob = build_description_html_blob("<p>Hello</p>")

    assert blob is not None
    expected_hash = compute_sha256_hex(b"<p>Hello</p>")
    assert blob.sha256 == expected_hash
    assert blob.key == f"job-html/{expected_hash}.html.gz"
    assert gzip.decompress(blob.data) == b"<p>Hello</p>"


def test_build_raw_payload_blob_canonicalizes_json_and_gzip() -> None:
    blob = build_raw_payload_blob({"b": 2, "a": 1})

    assert blob is not None
    expected_json = b'{"a":1,"b":2}'
    expected_hash = compute_sha256_hex(expected_json)
    assert blob.sha256 == expected_hash
    assert blob.key == f"job-raw/{expected_hash}.json.gz"
    assert gzip.decompress(blob.data) == expected_json


@pytest.mark.asyncio
async def test_job_blob_manager_skips_upload_when_hash_is_unchanged() -> None:
    storage = _InMemoryBlobStorage()
    manager = JobBlobManager(storage)
    job = _build_job()

    html_blob = build_description_html_blob(job.description_html)
    raw_blob = build_raw_payload_blob(job.raw_payload)
    assert html_blob is not None
    assert raw_blob is not None

    existing_pointers = JobBlobPointers(
        description_html_key=html_blob.key,
        description_html_hash=html_blob.sha256,
        raw_payload_key=raw_blob.key,
        raw_payload_hash=raw_blob.sha256,
    )

    result = await manager.sync_job_blobs(job, existing_pointers=existing_pointers)

    assert result.upload_count == 0
    assert storage.upload_calls == []
    assert job.description_html_key == html_blob.key
    assert job.raw_payload_key == raw_blob.key


@pytest.mark.asyncio
async def test_job_blob_manager_loaders_fallback_to_storage() -> None:
    storage = _InMemoryBlobStorage()
    manager = JobBlobManager(storage)

    html_blob = build_description_html_blob("<p>Hello</p>")
    raw_blob = build_raw_payload_blob({"a": 1})
    assert html_blob is not None
    assert raw_blob is not None
    storage.objects[html_blob.key] = html_blob.data
    storage.objects[raw_blob.key] = raw_blob.data

    job = Job(
        id="job-2",
        source="greenhouse:acme",
        external_job_id="456",
        title="Engineer",
        apply_url="https://example.com/jobs/456",
        description_html=None,
        description_html_key=html_blob.key,
        raw_payload={},
        raw_payload_key=raw_blob.key,
    )

    assert await manager.load_description_html(job) == "<p>Hello</p>"
    assert await manager.load_raw_payload(job) == {"a": 1}


@pytest.mark.asyncio
async def test_supabase_blob_storage_upload_if_missing_checks_info_then_upload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/object/info/jobs/job-html/test.html.gz"):
            return httpx.Response(status_code=404)
        if request.url.path.endswith("/object/jobs/job-html/test.html.gz"):
            return httpx.Response(status_code=200, json={"Key": "job-html/test.html.gz"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    storage = SupabaseBlobStorage(
        base_url="https://example.supabase.co/storage/v1",
        bucket="jobs",
        service_key="service-key",
        transport=httpx.MockTransport(handler),
    )

    uploaded = await storage.upload_if_missing(
        key="job-html/test.html.gz",
        data=gzip.compress(b"<p>Hello</p>", mtime=0),
        content_type="text/html; charset=utf-8",
    )

    assert uploaded is True
    assert len(requests) == 2
    assert requests[0].headers["authorization"] == "Bearer service-key"
    assert requests[1].headers["content-encoding"] == "gzip"
    assert requests[1].headers["x-upsert"] == "false"
    assert requests[1].method == "POST"
    assert requests[1].headers["content-type"] == "text/html; charset=utf-8"
    assert bytes(requests[1].content).startswith(b"\x1f\x8b")


@pytest.mark.asyncio
async def test_supabase_blob_storage_accepts_400_not_found_info_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/object/info/jobs/job-html/test-400.html.gz"):
            return httpx.Response(
                status_code=400,
                json={"statusCode": "404", "error": "not_found", "message": "Object not found"},
            )
        if request.url.path.endswith("/object/jobs/job-html/test-400.html.gz"):
            return httpx.Response(status_code=200, json={"Key": "job-html/test-400.html.gz"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    storage = SupabaseBlobStorage(
        base_url="https://example.supabase.co/storage/v1",
        bucket="jobs",
        service_key="service-key",
        transport=httpx.MockTransport(handler),
    )

    uploaded = await storage.upload_if_missing(
        key="job-html/test-400.html.gz",
        data=gzip.compress(b"<p>Hello</p>", mtime=0),
        content_type="text/html; charset=utf-8",
    )

    assert uploaded is True
    assert len(requests) == 2


@pytest.mark.asyncio
async def test_supabase_blob_storage_retries_transient_5xx_on_info_lookup() -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/object/info/jobs/job-html/retry.html.gz"):
            attempts["count"] += 1
            if attempts["count"] < 3:
                return httpx.Response(status_code=500, text="temporary")
            return httpx.Response(
                status_code=400,
                json={"statusCode": "404", "error": "not_found", "message": "Object not found"},
            )
        if request.url.path.endswith("/object/jobs/job-html/retry.html.gz"):
            return httpx.Response(status_code=200, json={"Key": "job-html/retry.html.gz"})
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    storage = SupabaseBlobStorage(
        base_url="https://example.supabase.co/storage/v1",
        bucket="jobs",
        service_key="service-key",
        transport=httpx.MockTransport(handler),
    )

    uploaded = await storage.upload_if_missing(
        key="job-html/retry.html.gz",
        data=gzip.compress(b"<p>Hello</p>", mtime=0),
        content_type="text/html; charset=utf-8",
    )

    assert uploaded is True
    assert attempts["count"] == 3
