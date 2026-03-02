from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from typing import Any

HTML_BLOB_PREFIX = "job-html"
RAW_BLOB_PREFIX = "job-raw"


@dataclass(frozen=True)
class PreparedBlob:
    """Prepared blob bytes plus its storage metadata."""

    key: str
    sha256: str
    content_type: str
    data: bytes


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
