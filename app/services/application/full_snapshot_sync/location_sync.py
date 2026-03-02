from __future__ import annotations

from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job
from app.services.domain.job_location import (
    StructuredLocation,
    sync_job_location,
    sync_primary_to_job,
)


async def sync_staged_job_locations(
    *,
    session: AsyncSession,
    staged_jobs: list[Job],
    unique_payloads: list[dict[str, Any]],
) -> None:
    payload_by_external_id = {
        str(payload["external_job_id"]): payload for payload in unique_payloads
    }
    for job in staged_jobs:
        payload = payload_by_external_id.get(str(job.external_job_id))
        if not payload:
            continue

        hints = payload.get("location_hints") or []
        for i, hint in enumerate(hints):
            is_primary = i == 0
            structured = StructuredLocation(**hint)

            location = await sync_job_location(
                session=session,
                job_id=str(job.id),
                structured=structured,
                is_primary=is_primary,
                source_raw=payload.get("location_text"),
            )

            if is_primary:
                sync_primary_to_job(
                    job=job,
                    location=location,
                    workplace_type=structured.workplace_type,
                    remote_scope=structured.remote_scope,
                )
