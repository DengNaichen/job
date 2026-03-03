from __future__ import annotations

from typing import Any

from app.ingest.mappers.base import BaseMapper

from .errors import FullSnapshotSyncError


def map_raw_jobs(
    *,
    raw_jobs: list[dict[str, Any]],
    mapper: BaseMapper,
    source_id: str,
    source_key: str,
) -> list[dict[str, Any]]:
    mapped_payloads: list[dict[str, Any]] = []
    for raw_job in raw_jobs:
        mapped = mapper.map(raw_job)
        payload = mapped.model_dump()
        external_job_id = str(payload.get("external_job_id") or "").strip()
        if not external_job_id:
            raise FullSnapshotSyncError("Mapped job is missing external_job_id")
        payload["external_job_id"] = external_job_id
        # Dual-write: authoritative source_id + compatibility source string
        payload["source_id"] = source_id
        payload["source"] = source_key
        mapped_payloads.append(payload)
    return mapped_payloads


def dedupe_by_external_job_id(mapped_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for payload in mapped_payloads:
        deduped[str(payload["external_job_id"])] = payload
    return list(deduped.values())
