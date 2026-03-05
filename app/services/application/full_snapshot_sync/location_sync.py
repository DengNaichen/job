from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Job, WorkplaceType
from app.services.domain.job_location import (
    StructuredLocation,
    parse_location_text,
    sync_job_location,
    sync_primary_to_job,
)


def _full_snapshot_geonames_resolver() -> Any:
    # Keep geonames lookup behind package export so tests can monkeypatch
    # app.services.application.full_snapshot_sync.get_geonames_resolver.
    import app.services.application.full_snapshot_sync as full_snapshot_sync

    return full_snapshot_sync.get_geonames_resolver()


def _clean_optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _coerce_workplace_type(value: object) -> WorkplaceType:
    if isinstance(value, WorkplaceType):
        return value
    if isinstance(value, str):
        try:
            return WorkplaceType(value)
        except ValueError:
            return WorkplaceType.unknown
    return WorkplaceType.unknown


def _is_structured_location_usable(location: StructuredLocation) -> bool:
    return bool(location.city or location.region or location.country_code)


@dataclass
class StructuredLocationPayload:
    structured: StructuredLocation
    source_raw: str | None = None


def _build_structured_locations(payload: dict[str, Any]) -> list[StructuredLocationPayload]:
    hints = payload.get("location_hints")
    structured_locations: list[StructuredLocationPayload] = []

    if isinstance(hints, list):
        for hint in hints:
            if not isinstance(hint, dict):
                continue
            source_raw = _clean_optional_str(hint.get("source_raw"))
            structured = StructuredLocation(
                city=_clean_optional_str(hint.get("city")),
                region=_clean_optional_str(hint.get("region")),
                country_code=_clean_optional_str(hint.get("country_code")),
                workplace_type=_coerce_workplace_type(hint.get("workplace_type")),
                remote_scope=_clean_optional_str(hint.get("remote_scope")),
            )

            if source_raw:
                parsed = parse_location_text(source_raw)
                structured.city = structured.city or parsed.city
                structured.region = structured.region or parsed.region
                structured.country_code = structured.country_code or parsed.country_code
                if structured.workplace_type == WorkplaceType.unknown:
                    structured.workplace_type = parsed.workplace_type
                structured.remote_scope = structured.remote_scope or parsed.remote_scope

            if not structured.country_code and structured.city:
                city_match = _full_snapshot_geonames_resolver().resolve_city(
                    city=structured.city,
                    region=structured.region,
                )
                if city_match:
                    structured.country_code = city_match.country_code
                    structured.region = structured.region or city_match.admin1_code

            if _is_structured_location_usable(structured):
                structured_locations.append(
                    StructuredLocationPayload(structured=structured, source_raw=source_raw)
                )

    if structured_locations:
        return structured_locations

    return []


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

        structured_locations = _build_structured_locations(payload)
        for i, location_payload in enumerate(structured_locations):
            is_primary = i == 0
            structured = location_payload.structured

            location = await sync_job_location(
                session=session,
                job_id=str(job.id),
                structured=structured,
                is_primary=is_primary,
                source_raw=location_payload.source_raw,
            )

            if is_primary:
                sync_primary_to_job(
                    job=job,
                    location=location,
                    workplace_type=structured.workplace_type,
                    remote_scope=structured.remote_scope,
                )
